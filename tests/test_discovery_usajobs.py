"""Tests for the USAJOBS adapter in :mod:`atlas.discovery.aggregators.usajobs`.

Listing is exercised offline through a scripted :class:`FakeFetcher` replaying a
recorded nested ``SearchResult`` payload — no real HTTP (AGENTS.md §6.2). The
credentials are asserted to appear in the request **headers** (the key difference
from Adzuna's query-string auth), and :func:`build_usajobs` is driven through a
:class:`FakeKeyring` for the enabled/disabled/keyless/no-email cases.
"""

from __future__ import annotations

import json

import pytest

from atlas.config.schema import UsajobsConfig
from atlas.config.secrets import SecretStore
from atlas.discovery.aggregators.structure import SavedSearch
from atlas.discovery.aggregators.usajobs import UsajobsAdapter, build_usajobs
from atlas.discovery.errors import DiscoveryError
from atlas.scrape.errors import FetchError
from atlas.scrape.fetcher import FetchResult
from tests.conftest import FakeFetcher, FakeKeyring

_TIMEOUT = 30

#: A recorded USAJOBS search payload — the nested SearchResult shape.
_PAYLOAD = {
    "SearchResult": {
        "SearchResultCount": 2,
        "SearchResultItems": [
            {
                "MatchedObjectId": "900",
                "MatchedObjectDescriptor": {
                    "PositionTitle": "Software Engineer",
                    "OrganizationName": "Department of Commerce",
                    "PositionURI": "https://www.usajobs.gov/job/900",
                    "PositionLocationDisplay": "Washington, DC",
                    "PublicationStartDate": "2026-07-15",
                    "UserArea": {
                        "Details": {"JobSummary": "&lt;p&gt;Build &amp; run systems.&lt;/p&gt;"}
                    },
                },
            },
            {
                # ApplyURI as a list; no UserArea exercises the summary guard.
                "MatchedObjectId": "901",
                "MatchedObjectDescriptor": {
                    "PositionTitle": "Data Scientist",
                    "OrganizationName": "NASA",
                    "ApplyURI": ["https://www.usajobs.gov/job/901"],
                    "PositionLocationDisplay": "Remote",
                },
            },
            # Descriptor missing → skipped.
            {"MatchedObjectId": "x"},
            # Missing title/url → skipped.
            {"MatchedObjectId": "y", "MatchedObjectDescriptor": {"OrganizationName": "Nope"}},
            # Not an object → skipped.
            "not-an-item",
        ],
    }
}


def _adapter() -> UsajobsAdapter:
    return UsajobsAdapter(email="sam@example.test", api_key="secret-key")


def _result(body: str) -> FetchResult:
    return FetchResult(
        url="https://data.usajobs.gov/api/search",
        status_code=200,
        content_type="application/json",
        body=body,
    )


def test_search_normalizes_and_sends_header_auth() -> None:
    fetcher = FakeFetcher(_result(json.dumps(_PAYLOAD)))
    postings = _adapter().search(SavedSearch(query=""), fetcher=fetcher, timeout_s=_TIMEOUT)
    assert [p.external_id for p in postings] == ["900", "901"]
    first = postings[0]
    assert first.posting.title == "Software Engineer"
    assert first.posting.company == "Department of Commerce"
    assert first.posting.apply_url == "https://www.usajobs.gov/job/900"
    assert first.posting.location == "Washington, DC"
    assert first.posting.description == "Build & run systems."  # unescaped + stripped
    assert first.posting.posted_at == "2026-07-15"
    second = postings[1]
    assert second.posting.apply_url == "https://www.usajobs.gov/job/901"  # ApplyURI list → first
    assert second.posting.description == ""  # no UserArea → empty summary
    # Auth travels in the headers, not the query string.
    call = fetcher.calls[0]
    assert call.url == "https://data.usajobs.gov/api/search?Keyword="
    assert call.headers == {
        "Host": "data.usajobs.gov",
        "User-Agent": "sam@example.test",
        "Authorization-Key": "secret-key",
    }
    assert call.timeout_s == _TIMEOUT


def test_search_encodes_location() -> None:
    fetcher = FakeFetcher(_result(json.dumps({"SearchResult": {"SearchResultItems": []}})))
    _adapter().search(
        SavedSearch(query="data science", location="New York"),
        fetcher=fetcher,
        timeout_s=_TIMEOUT,
    )
    assert fetcher.calls[0].url == (
        "https://data.usajobs.gov/api/search?Keyword=data+science&LocationName=New+York"
    )


def test_search_non_json_raises() -> None:
    fetcher = FakeFetcher(_result("<html>nope</html>"))
    with pytest.raises(DiscoveryError, match="non-JSON"):
        _adapter().search(SavedSearch(query="x"), fetcher=fetcher, timeout_s=_TIMEOUT)


def test_search_missing_items_raises() -> None:
    fetcher = FakeFetcher(_result(json.dumps({"SearchResult": {}})))
    with pytest.raises(DiscoveryError, match="SearchResultItems"):
        _adapter().search(SavedSearch(query="x"), fetcher=fetcher, timeout_s=_TIMEOUT)


def test_search_missing_search_result_raises() -> None:
    fetcher = FakeFetcher(_result("[]"))
    with pytest.raises(DiscoveryError, match="SearchResultItems"):
        _adapter().search(SavedSearch(query="x"), fetcher=fetcher, timeout_s=_TIMEOUT)


def test_search_user_area_without_details_leaves_summary_empty() -> None:
    payload = {
        "SearchResult": {
            "SearchResultItems": [
                {
                    "MatchedObjectId": "1",
                    "MatchedObjectDescriptor": {
                        "PositionTitle": "Role",
                        "PositionURI": "https://www.usajobs.gov/job/1",
                        # UserArea present but Details missing → summary stays "".
                        "UserArea": {"IsRadialSearch": False},
                    },
                }
            ]
        }
    }
    fetcher = FakeFetcher(_result(json.dumps(payload)))
    postings = _adapter().search(SavedSearch(query=""), fetcher=fetcher, timeout_s=_TIMEOUT)
    assert len(postings) == 1
    assert postings[0].posting.description == ""


def test_search_item_with_empty_apply_list_is_skipped() -> None:
    payload = {
        "SearchResult": {
            "SearchResultItems": [
                {
                    "MatchedObjectId": "1",
                    "MatchedObjectDescriptor": {"PositionTitle": "Role", "ApplyURI": []},
                }
            ]
        }
    }
    fetcher = FakeFetcher(_result(json.dumps(payload)))
    assert _adapter().search(SavedSearch(query=""), fetcher=fetcher, timeout_s=_TIMEOUT) == []


def test_search_propagates_fetch_error() -> None:
    fetcher = FakeFetcher(raises=FetchError("boom"))
    with pytest.raises(FetchError):
        _adapter().search(SavedSearch(query="x"), fetcher=fetcher, timeout_s=_TIMEOUT)


def test_build_usajobs_returns_none_when_disabled(fake_keyring: FakeKeyring) -> None:
    store = SecretStore(fake_keyring)
    store.set("usajobs", "key")
    assert build_usajobs(UsajobsConfig(enabled=False, email="sam@example.test"), store) is None


def test_build_usajobs_returns_none_without_email(fake_keyring: FakeKeyring) -> None:
    store = SecretStore(fake_keyring)
    store.set("usajobs", "key")
    assert build_usajobs(UsajobsConfig(enabled=True, email=""), store) is None


def test_build_usajobs_returns_none_without_key(fake_keyring: FakeKeyring) -> None:
    store = SecretStore(fake_keyring)
    assert build_usajobs(UsajobsConfig(enabled=True, email="sam@example.test"), store) is None


def test_build_usajobs_builds_when_configured(fake_keyring: FakeKeyring) -> None:
    store = SecretStore(fake_keyring)
    store.set("usajobs", "key")
    adapter = build_usajobs(UsajobsConfig(enabled=True, email="sam@example.test"), store)
    assert isinstance(adapter, UsajobsAdapter)
