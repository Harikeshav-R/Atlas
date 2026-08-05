"""Tests for the RemoteOK adapter in :mod:`atlas.discovery.aggregators.remoteok`.

Listing is exercised offline through a scripted :class:`FakeFetcher` replaying a
recorded feed payload — the leading legal/metadata notice, real jobs, and malformed
rows — with no real HTTP (AGENTS.md §6.2). Query/location filtering is asserted
here end-to-end (the shared filter is unit-tested in ``test_discovery_filters``).
"""

from __future__ import annotations

import json

import pytest

from atlas.discovery.aggregators.remoteok import RemoteOKAdapter
from atlas.discovery.aggregators.structure import SavedSearch
from atlas.discovery.errors import DiscoveryError
from atlas.scrape.errors import FetchError
from atlas.scrape.fetcher import FetchResult
from tests.conftest import FakeFetcher

_TIMEOUT = 30

#: A recorded RemoteOK feed — a raw JSON ARRAY whose first element is the
#: legal/metadata notice (not a job), followed by jobs and malformed rows.
_FEED = [
    {"legal": "RemoteOK API notice — no id/position here."},
    {
        "id": 1001,
        "slug": "backend-engineer-acme",
        "company": "Acme",
        "position": "Senior Python Backend Engineer",
        "location": "Worldwide",
        "tags": ["python", "backend", "django"],
        "description": "&lt;p&gt;Build &amp; scale services.&lt;/p&gt;",
        "url": "https://remoteok.com/remote-jobs/1001",
        "date": "2026-08-01T00:00:00+00:00",
    },
    {
        # No numeric id → falls back to slug; no tags key exercises the guard.
        "slug": "ml-engineer-globex",
        "company": "Globex",
        "position": "Machine Learning Engineer",
        "location": "US only",
        "description": "Train models.",
        "url": "https://remoteok.com/remote-jobs/ml-engineer-globex",
    },
    # Malformed: missing position/url — skipped, not fatal.
    {"id": 9, "company": "NoTitle"},
    # Not even an object — skipped (as is the leading notice dict, which lacks id).
    "not-a-posting",
]


def _result(body: str) -> FetchResult:
    return FetchResult(
        url="https://remoteok.com/api",
        status_code=200,
        content_type="application/json",
        body=body,
    )


def test_search_normalizes_feed_and_skips_notice() -> None:
    fetcher = FakeFetcher(_result(json.dumps(_FEED)))
    postings = RemoteOKAdapter().search(SavedSearch(query=""), fetcher=fetcher, timeout_s=_TIMEOUT)
    assert [p.external_id for p in postings] == ["1001", "ml-engineer-globex"]
    first = postings[0]
    assert first.posting.title == "Senior Python Backend Engineer"
    assert first.posting.company == "Acme"
    assert first.posting.apply_url == "https://remoteok.com/remote-jobs/1001"
    assert first.posting.location == "Worldwide"
    assert first.posting.remote_type == "remote"
    assert first.posting.keywords == ["python", "backend", "django"]
    assert first.posting.description == "Build & scale services."  # unescaped + stripped
    assert first.posting.posted_at == "2026-08-01T00:00:00+00:00"
    second = postings[1]
    assert second.posting.company == "Globex"
    assert second.posting.keywords == []  # no tags → empty
    assert fetcher.calls[0].url == "https://remoteok.com/api"
    assert fetcher.calls[0].timeout_s == _TIMEOUT


def test_search_filters_by_query() -> None:
    fetcher = FakeFetcher(_result(json.dumps(_FEED)))
    postings = RemoteOKAdapter().search(
        SavedSearch(query="machine learning"), fetcher=fetcher, timeout_s=_TIMEOUT
    )
    assert [p.external_id for p in postings] == ["ml-engineer-globex"]


def test_search_filters_by_location() -> None:
    fetcher = FakeFetcher(_result(json.dumps(_FEED)))
    postings = RemoteOKAdapter().search(
        SavedSearch(query="", location="worldwide"), fetcher=fetcher, timeout_s=_TIMEOUT
    )
    assert [p.external_id for p in postings] == ["1001"]


def test_search_empty_feed() -> None:
    fetcher = FakeFetcher(_result("[]"))
    assert (
        RemoteOKAdapter().search(SavedSearch(query=""), fetcher=fetcher, timeout_s=_TIMEOUT) == []
    )


def test_search_non_json_raises() -> None:
    fetcher = FakeFetcher(_result("<html>nope</html>"))
    with pytest.raises(DiscoveryError, match="non-JSON"):
        RemoteOKAdapter().search(SavedSearch(query=""), fetcher=fetcher, timeout_s=_TIMEOUT)


def test_search_non_list_raises() -> None:
    fetcher = FakeFetcher(_result('{"jobs": []}'))
    with pytest.raises(DiscoveryError, match="postings list"):
        RemoteOKAdapter().search(SavedSearch(query=""), fetcher=fetcher, timeout_s=_TIMEOUT)


def test_search_propagates_fetch_error() -> None:
    fetcher = FakeFetcher(raises=FetchError("boom"))
    with pytest.raises(FetchError):
        RemoteOKAdapter().search(SavedSearch(query=""), fetcher=fetcher, timeout_s=_TIMEOUT)
