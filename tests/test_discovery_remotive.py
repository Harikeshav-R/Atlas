"""Tests for the Remotive adapter in :mod:`atlas.discovery.aggregators.remotive`.

Listing is exercised offline through a scripted :class:`FakeFetcher` replaying a
recorded ``{"jobs": [...]}`` payload — no real HTTP (AGENTS.md §6.2). The adapter
passes the query to the API's ``search`` parameter and applies the location/remote
filters in code.
"""

from __future__ import annotations

import json

import pytest

from atlas.discovery.aggregators.remotive import RemotiveAdapter
from atlas.discovery.aggregators.structure import SavedSearch
from atlas.discovery.errors import DiscoveryError
from atlas.scrape.errors import FetchError
from atlas.scrape.fetcher import FetchResult
from tests.conftest import FakeFetcher

_TIMEOUT = 30

#: A recorded Remotive API payload — a wrapped object with a "jobs" array.
_PAYLOAD = {
    "job-count": 2,
    "jobs": [
        {
            "id": 500,
            "company_name": "Acme",
            "title": "Backend Engineer",
            "url": "https://remotive.com/remote-jobs/backend-engineer-500",
            "candidate_required_location": "Worldwide",
            "tags": ["python", "backend"],
            "job_type": "full_time",
            "description": "&lt;p&gt;Build APIs &amp; services.&lt;/p&gt;",
            "publication_date": "2026-07-30T12:00:00",
        },
        {
            # No tags key exercises the guard.
            "id": 501,
            "company_name": "Globex",
            "title": "Frontend Engineer",
            "url": "https://remotive.com/remote-jobs/frontend-engineer-501",
            "candidate_required_location": "USA Only",
            "job_type": "contract",
            "description": "Ship UI.",
        },
        # Malformed: missing title/url — skipped, not fatal.
        {"id": 9, "company_name": "NoTitle"},
        # Not even an object — skipped.
        "not-a-job",
    ],
}


def _result(body: str) -> FetchResult:
    return FetchResult(
        url="https://remotive.com/api/remote-jobs?search=engineer",
        status_code=200,
        content_type="application/json",
        body=body,
    )


def test_search_normalizes_jobs_and_passes_query() -> None:
    fetcher = FakeFetcher(_result(json.dumps(_PAYLOAD)))
    postings = RemotiveAdapter().search(
        SavedSearch(query="engineer"), fetcher=fetcher, timeout_s=_TIMEOUT
    )
    assert [p.external_id for p in postings] == ["500", "501"]
    first = postings[0]
    assert first.posting.title == "Backend Engineer"
    assert first.posting.company == "Acme"
    assert first.posting.apply_url == "https://remotive.com/remote-jobs/backend-engineer-500"
    assert first.posting.location == "Worldwide"
    assert first.posting.employment_type == "full_time"
    assert first.posting.remote_type == "remote"
    assert first.posting.keywords == ["python", "backend"]
    assert first.posting.description == "Build APIs & services."  # unescaped + stripped
    assert first.posting.posted_at == "2026-07-30T12:00:00"
    assert postings[1].posting.keywords == []  # no tags → empty
    # The query is URL-encoded into the API's search parameter.
    assert fetcher.calls[0].url == "https://remotive.com/api/remote-jobs?search=engineer"
    assert fetcher.calls[0].timeout_s == _TIMEOUT


def test_search_encodes_multiword_query() -> None:
    fetcher = FakeFetcher(_result(json.dumps({"jobs": []})))
    RemotiveAdapter().search(
        SavedSearch(query="python backend"), fetcher=fetcher, timeout_s=_TIMEOUT
    )
    assert fetcher.calls[0].url == "https://remotive.com/api/remote-jobs?search=python+backend"


def test_search_filters_by_location() -> None:
    fetcher = FakeFetcher(_result(json.dumps(_PAYLOAD)))
    postings = RemotiveAdapter().search(
        SavedSearch(query="engineer", location="usa"), fetcher=fetcher, timeout_s=_TIMEOUT
    )
    assert [p.external_id for p in postings] == ["501"]


def test_search_non_json_raises() -> None:
    fetcher = FakeFetcher(_result("<html>nope</html>"))
    with pytest.raises(DiscoveryError, match="non-JSON"):
        RemotiveAdapter().search(SavedSearch(query="x"), fetcher=fetcher, timeout_s=_TIMEOUT)


def test_search_missing_jobs_raises() -> None:
    fetcher = FakeFetcher(_result("[]"))
    with pytest.raises(DiscoveryError, match="'jobs' list"):
        RemotiveAdapter().search(SavedSearch(query="x"), fetcher=fetcher, timeout_s=_TIMEOUT)


def test_search_propagates_fetch_error() -> None:
    fetcher = FakeFetcher(raises=FetchError("boom"))
    with pytest.raises(FetchError):
        RemotiveAdapter().search(SavedSearch(query="x"), fetcher=fetcher, timeout_s=_TIMEOUT)
