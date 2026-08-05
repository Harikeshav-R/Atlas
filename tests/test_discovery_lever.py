"""Tests for the Lever adapter in :mod:`atlas.discovery.ats.lever`.

Detection is pure over URL strings; listing is exercised offline through a
scripted :class:`FakeFetcher` replaying a recorded raw-array payload — no real
HTTP (AGENTS.md §6.2).
"""

from __future__ import annotations

import json

import pytest

from atlas.discovery.ats.lever import LeverAdapter
from atlas.discovery.errors import DiscoveryError
from atlas.scrape.errors import FetchError
from atlas.scrape.fetcher import FetchResult
from tests.conftest import FakeFetcher

_TIMEOUT = 30

#: A recorded Lever postings payload — a raw JSON ARRAY (not wrapped).
_POSTINGS = [
    {
        "id": "abc-123",
        "text": "Backend Engineer",
        "hostedUrl": "https://jobs.lever.co/acme/abc-123",
        "applyUrl": "https://jobs.lever.co/acme/abc-123/apply",
        "categories": {"location": "Remote - US", "commitment": "Full-time", "team": "Platform"},
        "workplaceType": "remote",
        "descriptionPlain": "Build reliable services.",
        "createdAt": 1737000000000,
    },
    {
        # No descriptionPlain → falls back to stripping the HTML description;
        # applyUrl is used when hostedUrl is absent; and no categories at all
        # exercises the missing-categories guard (location/team stay None).
        "id": "def-456",
        "text": "ML Engineer",
        "applyUrl": "https://jobs.lever.co/acme/def-456/apply",
        "description": "&lt;p&gt;Train &amp; ship models.&lt;/p&gt;",
    },
    # Malformed: missing id/text/apply-url — skipped, not fatal.
    {"text": "No id here"},
    # Not even an object — skipped.
    "not-a-posting",
]


def _result(body: str) -> FetchResult:
    return FetchResult(
        url="https://api.lever.co/v0/postings/acme?mode=json",
        status_code=200,
        content_type="application/json",
        body=body,
    )


@pytest.mark.parametrize(
    ("url", "token"),
    [
        ("https://jobs.lever.co/acme", "acme"),
        ("https://jobs.lever.co/acme/abc-123", "acme"),
        ("https://jobs.eu.lever.co/acme", "acme"),
        ("HTTPS://Jobs.Lever.CO/Acme/", "Acme"),
        ("https://api.lever.co/v0/postings/acme", "acme"),
        ("https://api.lever.co/v0/postings/acme?mode=json", "acme"),
        ("https://api.eu.lever.co/v0/postings/acme", "acme"),
    ],
)
def test_detect_recognizes_urls(url: str, token: str) -> None:
    assert LeverAdapter().detect(url) == token


@pytest.mark.parametrize(
    "url",
    [
        "https://boards.greenhouse.io/acme",  # a different ATS
        "https://example.com/careers",  # not lever
        "https://jobs.lever.co/",  # no site segment
        "https://api.lever.co/v0/postings",  # no site after "postings"
        "https://api.lever.co/v0/other",  # no "postings" segment
    ],
)
def test_detect_rejects_unrecognized_urls(url: str) -> None:
    assert LeverAdapter().detect(url) is None


def test_list_postings_normalizes_raw_array() -> None:
    fetcher = FakeFetcher(_result(json.dumps(_POSTINGS)))
    postings = LeverAdapter().list_postings("acme", fetcher=fetcher, timeout_s=_TIMEOUT)
    assert [p.external_id for p in postings] == ["abc-123", "def-456"]
    first = postings[0]
    assert first.posting.title == "Backend Engineer"
    assert first.posting.apply_url == "https://jobs.lever.co/acme/abc-123"  # hostedUrl preferred
    assert first.posting.location == "Remote - US"
    assert first.posting.employment_type == "Full-time"
    assert first.posting.team == "Platform"
    assert first.posting.remote_type == "remote"
    assert first.posting.description == "Build reliable services."
    assert first.posting.posted_at == "1737000000000"
    second = postings[1]
    assert (
        second.posting.apply_url == "https://jobs.lever.co/acme/def-456/apply"
    )  # applyUrl fallback
    assert second.posting.description == "Train & ship models."  # HTML unescaped + stripped
    assert second.posting.location is None  # no categories → location stays None
    assert fetcher.calls[0].url == "https://api.lever.co/v0/postings/acme?mode=json"
    assert fetcher.calls[0].timeout_s == _TIMEOUT


def test_list_postings_empty_board() -> None:
    fetcher = FakeFetcher(_result("[]"))
    assert LeverAdapter().list_postings("acme", fetcher=fetcher, timeout_s=_TIMEOUT) == []


def test_list_postings_non_json_raises() -> None:
    fetcher = FakeFetcher(_result("<html>nope</html>"))
    with pytest.raises(DiscoveryError, match="non-JSON"):
        LeverAdapter().list_postings("acme", fetcher=fetcher, timeout_s=_TIMEOUT)


def test_list_postings_non_list_raises() -> None:
    fetcher = FakeFetcher(_result('{"postings": []}'))
    with pytest.raises(DiscoveryError, match="postings list"):
        LeverAdapter().list_postings("acme", fetcher=fetcher, timeout_s=_TIMEOUT)


def test_list_postings_propagates_fetch_error() -> None:
    fetcher = FakeFetcher(raises=FetchError("boom"))
    with pytest.raises(FetchError):
        LeverAdapter().list_postings("acme", fetcher=fetcher, timeout_s=_TIMEOUT)
