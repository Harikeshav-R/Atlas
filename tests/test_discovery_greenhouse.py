"""Tests for the Greenhouse adapter in :mod:`atlas.discovery.ats.greenhouse`.

Detection is pure over URL strings; listing is exercised offline through a
scripted :class:`FakeFetcher` replaying a recorded board payload — no real HTTP
(AGENTS.md §6.2).
"""

from __future__ import annotations

import json

import pytest

from atlas.discovery.ats.greenhouse import GreenhouseAdapter
from atlas.discovery.errors import DiscoveryError
from atlas.scrape.errors import FetchError
from atlas.scrape.fetcher import FetchResult
from tests.conftest import FakeFetcher

_TIMEOUT = 30

#: A recorded Greenhouse board payload (two jobs + one malformed job to skip).
_BOARD = {
    "jobs": [
        {
            "id": 127817,
            "internal_job_id": 144381,
            "title": "Backend Engineer",
            "updated_at": "2026-01-14T10:55:28-05:00",
            "location": {"name": "Remote - US"},
            "absolute_url": "https://boards.greenhouse.io/acme/jobs/127817",
            "content": "&lt;p&gt;Build &amp; run reliable services.&lt;/p&gt;",
        },
        {
            "id": 200002,
            "title": "ML Engineer",
            "updated_at": "2026-02-01T09:00:00-05:00",
            "location": None,
            "absolute_url": "https://boards.greenhouse.io/acme/jobs/200002",
            "content": None,
        },
        # Malformed: no id / title / absolute_url — must be skipped, not fatal.
        {"internal_job_id": 999},
        # Not even an object — must be skipped, not fatal.
        "not-a-job",
    ],
    "meta": {"total": 4},
}


def _result(body: str) -> FetchResult:
    return FetchResult(
        url="https://boards-api.greenhouse.io/v1/boards/acme/jobs?content=true",
        status_code=200,
        content_type="application/json",
        body=body,
    )


@pytest.mark.parametrize(
    ("url", "token"),
    [
        ("https://boards.greenhouse.io/acme", "acme"),
        ("https://boards.greenhouse.io/acme/jobs/127817", "acme"),
        ("https://job-boards.greenhouse.io/acme", "acme"),
        ("HTTPS://Boards.Greenhouse.IO/Acme/", "Acme"),
        ("https://boards.greenhouse.io/embed/job_board?for=acme", "acme"),
        ("https://acme.greenhouse.io", "acme"),
        ("https://acme.greenhouse.io/careers", "acme"),
    ],
)
def test_detect_recognizes_board_urls(url: str, token: str) -> None:
    assert GreenhouseAdapter().detect(url) == token


@pytest.mark.parametrize(
    "url",
    [
        "https://jobs.lever.co/acme",  # a different ATS host
        "https://example.com/careers",  # not greenhouse at all
        "https://boards.greenhouse.io/embed/job_board",  # embed with no ?for=
        "https://boards.greenhouse.io/",  # no token segment
        "https://boards.greenhouse.io/embed",  # reserved first segment, no token
        "https://www.greenhouse.io",  # reserved subdomain
    ],
)
def test_detect_rejects_unrecognized_urls(url: str) -> None:
    assert GreenhouseAdapter().detect(url) is None


def test_list_postings_normalizes_jobs() -> None:
    fetcher = FakeFetcher(_result(json.dumps(_BOARD)))
    postings = GreenhouseAdapter().list_postings("acme", fetcher=fetcher, timeout_s=_TIMEOUT)
    # The malformed third job is skipped.
    assert [p.external_id for p in postings] == ["127817", "200002"]
    first = postings[0]
    assert first.posting.title == "Backend Engineer"
    assert first.posting.apply_url == "https://boards.greenhouse.io/acme/jobs/127817"
    assert first.posting.location == "Remote - US"
    assert first.posting.posted_at == "2026-01-14T10:55:28-05:00"
    # content is HTML-escaped HTML → unescaped and stripped to visible text.
    assert first.posting.description == "Build & run reliable services."
    # A job with no location / no content still normalizes.
    assert postings[1].posting.location is None
    assert postings[1].posting.description == ""
    # The board URL carries the token and content=true.
    assert fetcher.calls[0].url == (
        "https://boards-api.greenhouse.io/v1/boards/acme/jobs?content=true"
    )
    assert fetcher.calls[0].timeout_s == _TIMEOUT


def test_list_postings_empty_board() -> None:
    fetcher = FakeFetcher(_result(json.dumps({"jobs": [], "meta": {"total": 0}})))
    assert GreenhouseAdapter().list_postings("acme", fetcher=fetcher, timeout_s=_TIMEOUT) == []


def test_list_postings_non_json_raises() -> None:
    fetcher = FakeFetcher(_result("<html>not json</html>"))
    with pytest.raises(DiscoveryError, match="non-JSON"):
        GreenhouseAdapter().list_postings("acme", fetcher=fetcher, timeout_s=_TIMEOUT)


@pytest.mark.parametrize("body", ['{"meta": {}}', "[]", '{"jobs": "nope"}'])
def test_list_postings_missing_jobs_raises(body: str) -> None:
    fetcher = FakeFetcher(_result(body))
    with pytest.raises(DiscoveryError, match="no 'jobs' list"):
        GreenhouseAdapter().list_postings("acme", fetcher=fetcher, timeout_s=_TIMEOUT)


def test_list_postings_propagates_fetch_error() -> None:
    fetcher = FakeFetcher(raises=FetchError("boom"))
    with pytest.raises(FetchError):
        GreenhouseAdapter().list_postings("acme", fetcher=fetcher, timeout_s=_TIMEOUT)
