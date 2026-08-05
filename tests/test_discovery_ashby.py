"""Tests for the Ashby adapter in :mod:`atlas.discovery.ats.ashby`.

Detection is pure over URL strings; listing is exercised offline through a
scripted :class:`FakeFetcher` replaying a recorded payload — no real HTTP
(AGENTS.md §6.2).
"""

from __future__ import annotations

import json

import pytest

from atlas.discovery.ats.ashby import AshbyAdapter
from atlas.discovery.errors import DiscoveryError
from atlas.scrape.errors import FetchError
from atlas.scrape.fetcher import FetchResult
from tests.conftest import FakeFetcher

_TIMEOUT = 30

_UUID_1 = "11111111-1111-1111-1111-111111111111"
_UUID_2 = "22222222-2222-2222-2222-222222222222"
_UUID_3 = "33333333-3333-3333-3333-333333333333"

#: A recorded Ashby job-board payload — jobs carry no top-level id.
_BOARD = {
    "apiVersion": "1",
    "jobs": [
        {
            "title": "Backend Engineer",
            "location": "Remote - US",
            "employmentType": "FullTime",
            "workplaceType": "Remote",
            "descriptionHtml": "&lt;p&gt;Build &amp; run services.&lt;/p&gt;",
            "descriptionPlain": "Build & run services.",
            "publishedAt": "2026-02-01T09:00:00Z",
            "jobUrl": f"https://jobs.ashbyhq.com/acme/{_UUID_1}",
            "applyUrl": f"https://jobs.ashbyhq.com/acme/{_UUID_1}/application",
            "isListed": True,
        },
        {
            # No descriptionPlain → strip descriptionHtml; no applyUrl → jobUrl is
            # the apply target AND the external-id source.
            "title": "ML Engineer",
            "location": "NYC",
            "descriptionHtml": "&lt;p&gt;Ship models.&lt;/p&gt;",
            "jobUrl": f"https://jobs.ashbyhq.com/acme/{_UUID_2}",
        },
        {
            # jobUrl reduces to an empty segment → the id falls through to applyUrl,
            # whose last path segment is the UUID.
            "title": "Data Engineer",
            "jobUrl": "https://jobs.ashbyhq.com/",
            "applyUrl": f"https://jobs.ashbyhq.com/acme/{_UUID_3}",
        },
        # Unlisted → skipped.
        {
            "title": "Hidden role",
            "jobUrl": "https://jobs.ashbyhq.com/acme/hidden",
            "isListed": False,
        },
        # No jobUrl/applyUrl → no derivable id → skipped.
        {"title": "No urls"},
        # Not an object → skipped.
        "not-a-job",
    ],
}


def _result(body: str) -> FetchResult:
    return FetchResult(
        url="https://api.ashbyhq.com/posting-api/job-board/acme?includeCompensation=false",
        status_code=200,
        content_type="application/json",
        body=body,
    )


@pytest.mark.parametrize(
    ("url", "token"),
    [
        ("https://jobs.ashbyhq.com/acme", "acme"),
        ("https://jobs.ashbyhq.com/acme/some-job", "acme"),
        ("HTTPS://Jobs.AshbyHQ.com/Acme/", "Acme"),
        ("https://api.ashbyhq.com/posting-api/job-board/acme", "acme"),
        ("https://api.ashbyhq.com/posting-api/job-board/acme?includeCompensation=true", "acme"),
    ],
)
def test_detect_recognizes_urls(url: str, token: str) -> None:
    assert AshbyAdapter().detect(url) == token


@pytest.mark.parametrize(
    "url",
    [
        "https://jobs.lever.co/acme",  # a different ATS
        "https://example.com/careers",  # not ashby
        "https://jobs.ashbyhq.com/",  # no name segment
        "https://api.ashbyhq.com/posting-api/job-board",  # no name after job-board
        "https://api.ashbyhq.com/other/path",  # no job-board segment
    ],
)
def test_detect_rejects_unrecognized_urls(url: str) -> None:
    assert AshbyAdapter().detect(url) is None


def test_list_postings_normalizes_jobs() -> None:
    fetcher = FakeFetcher(_result(json.dumps(_BOARD)))
    postings = AshbyAdapter().list_postings("acme", fetcher=fetcher, timeout_s=_TIMEOUT)
    # Unlisted, no-urls, and non-dict jobs are skipped.
    assert [p.external_id for p in postings] == [_UUID_1, _UUID_2, _UUID_3]
    first = postings[0]
    assert first.posting.title == "Backend Engineer"
    assert first.posting.apply_url == f"https://jobs.ashbyhq.com/acme/{_UUID_1}/application"
    assert first.posting.location == "Remote - US"
    assert first.posting.employment_type == "FullTime"
    assert first.posting.remote_type == "Remote"
    assert first.posting.description == "Build & run services."  # descriptionPlain
    assert first.posting.posted_at == "2026-02-01T09:00:00Z"
    second = postings[1]
    # No applyUrl → jobUrl is both the apply target and the id source.
    assert second.posting.apply_url == f"https://jobs.ashbyhq.com/acme/{_UUID_2}"
    assert second.posting.description == "Ship models."  # HTML stripped
    assert fetcher.calls[0].url == (
        "https://api.ashbyhq.com/posting-api/job-board/acme?includeCompensation=false"
    )


def test_list_postings_empty_board() -> None:
    fetcher = FakeFetcher(_result(json.dumps({"apiVersion": "1", "jobs": []})))
    assert AshbyAdapter().list_postings("acme", fetcher=fetcher, timeout_s=_TIMEOUT) == []


def test_list_postings_non_json_raises() -> None:
    fetcher = FakeFetcher(_result("<html>nope</html>"))
    with pytest.raises(DiscoveryError, match="non-JSON"):
        AshbyAdapter().list_postings("acme", fetcher=fetcher, timeout_s=_TIMEOUT)


@pytest.mark.parametrize("body", ['{"apiVersion": "1"}', "[]", '{"jobs": "nope"}'])
def test_list_postings_missing_jobs_raises(body: str) -> None:
    fetcher = FakeFetcher(_result(body))
    with pytest.raises(DiscoveryError, match="no 'jobs' list"):
        AshbyAdapter().list_postings("acme", fetcher=fetcher, timeout_s=_TIMEOUT)


def test_list_postings_propagates_fetch_error() -> None:
    fetcher = FakeFetcher(raises=FetchError("boom"))
    with pytest.raises(FetchError):
        AshbyAdapter().list_postings("acme", fetcher=fetcher, timeout_s=_TIMEOUT)
