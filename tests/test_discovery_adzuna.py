"""Tests for the Adzuna adapter in :mod:`atlas.discovery.aggregators.adzuna`.

Listing is exercised offline through a scripted :class:`FakeFetcher` replaying a
recorded ``{"results": [...]}`` payload — no real HTTP (AGENTS.md §6.2). The
credentials are asserted to appear in the fetched query string, and
:func:`build_adzuna` is driven through a :class:`FakeKeyring` for the
enabled/disabled/keyless cases.
"""

from __future__ import annotations

import json

import pytest

from atlas.config.schema import AdzunaConfig
from atlas.config.secrets import SecretStore
from atlas.discovery.aggregators.adzuna import AdzunaAdapter, build_adzuna
from atlas.discovery.aggregators.structure import SavedSearch
from atlas.discovery.errors import DiscoveryError
from atlas.scrape.errors import FetchError
from atlas.scrape.fetcher import FetchResult
from tests.conftest import FakeFetcher, FakeKeyring

_TIMEOUT = 30

#: A recorded Adzuna search payload — a wrapped object with a "results" array.
_PAYLOAD = {
    "count": 2,
    "results": [
        {
            "id": "100",
            "title": "Senior Python Engineer",
            "company": {"display_name": "Acme"},
            "location": {"display_name": "Remote, US"},
            "redirect_url": "https://www.adzuna.com/jobs/land/ad/100",
            "description": "&lt;p&gt;Build &amp; scale services.&lt;/p&gt;",
            "created": "2026-08-01T00:00:00Z",
        },
        {
            # No company/location dicts exercises the missing-nested guards.
            "id": "101",
            "title": "Machine Learning Engineer",
            "redirect_url": "https://www.adzuna.com/jobs/land/ad/101",
            "description": "Train models.",
        },
        # Malformed: missing id/title/url — skipped, not fatal.
        {"title": "No id here"},
        # Not even an object — skipped.
        "not-a-result",
    ],
}


def _adapter() -> AdzunaAdapter:
    return AdzunaAdapter(app_id="app-1", app_key="secret-key", country="us")


def _result(body: str) -> FetchResult:
    return FetchResult(
        url="https://api.adzuna.com/v1/api/jobs/us/search/1",
        status_code=200,
        content_type="application/json",
        body=body,
    )


def test_search_normalizes_and_sends_credentials() -> None:
    fetcher = FakeFetcher(_result(json.dumps(_PAYLOAD)))
    postings = _adapter().search(SavedSearch(query="engineer"), fetcher=fetcher, timeout_s=_TIMEOUT)
    assert [p.external_id for p in postings] == ["100", "101"]
    first = postings[0]
    assert first.posting.title == "Senior Python Engineer"
    assert first.posting.company == "Acme"
    assert first.posting.apply_url == "https://www.adzuna.com/jobs/land/ad/100"
    assert first.posting.location == "Remote, US"
    assert first.posting.description == "Build & scale services."  # unescaped + stripped
    assert first.posting.posted_at == "2026-08-01T00:00:00Z"
    assert postings[1].posting.company == ""  # no company dict → empty
    assert postings[1].posting.location is None  # no location dict → None
    # Credentials + query are in the fetched URL; the country is in the path.
    url = fetcher.calls[0].url
    assert url.startswith("https://api.adzuna.com/v1/api/jobs/us/search/1?")
    assert "app_id=app-1" in url
    assert "app_key=secret-key" in url
    assert "what=engineer" in url
    assert fetcher.calls[0].timeout_s == _TIMEOUT


def test_search_encodes_location() -> None:
    fetcher = FakeFetcher(_result(json.dumps({"results": []})))
    _adapter().search(
        SavedSearch(query="python dev", location="New York"), fetcher=fetcher, timeout_s=_TIMEOUT
    )
    url = fetcher.calls[0].url
    assert "what=python+dev" in url
    assert "where=New+York" in url


def test_search_omits_location_when_absent() -> None:
    fetcher = FakeFetcher(_result(json.dumps({"results": []})))
    _adapter().search(SavedSearch(query="python"), fetcher=fetcher, timeout_s=_TIMEOUT)
    assert "where=" not in fetcher.calls[0].url


def test_search_non_json_raises() -> None:
    fetcher = FakeFetcher(_result("<html>nope</html>"))
    with pytest.raises(DiscoveryError, match="non-JSON"):
        _adapter().search(SavedSearch(query="x"), fetcher=fetcher, timeout_s=_TIMEOUT)


def test_search_missing_results_raises() -> None:
    fetcher = FakeFetcher(_result("[]"))
    with pytest.raises(DiscoveryError, match="'results' list"):
        _adapter().search(SavedSearch(query="x"), fetcher=fetcher, timeout_s=_TIMEOUT)


def test_search_propagates_fetch_error() -> None:
    fetcher = FakeFetcher(raises=FetchError("boom"))
    with pytest.raises(FetchError):
        _adapter().search(SavedSearch(query="x"), fetcher=fetcher, timeout_s=_TIMEOUT)


def test_build_adzuna_returns_none_when_disabled(fake_keyring: FakeKeyring) -> None:
    store = SecretStore(fake_keyring)
    store.set("adzuna_app_id", "id")
    store.set("adzuna_app_key", "key")
    assert build_adzuna(AdzunaConfig(enabled=False), store) is None


def test_build_adzuna_returns_none_without_keys(fake_keyring: FakeKeyring) -> None:
    store = SecretStore(fake_keyring)
    # Enabled but neither key stored.
    assert build_adzuna(AdzunaConfig(enabled=True), store) is None
    # One key present is still not enough.
    store.set("adzuna_app_id", "id")
    assert build_adzuna(AdzunaConfig(enabled=True), store) is None


def test_build_adzuna_builds_when_enabled_and_keyed(fake_keyring: FakeKeyring) -> None:
    store = SecretStore(fake_keyring)
    store.set("adzuna_app_id", "id")
    store.set("adzuna_app_key", "key")
    adapter = build_adzuna(AdzunaConfig(enabled=True, country="gb"), store)
    assert isinstance(adapter, AdzunaAdapter)
    fetcher = FakeFetcher(_result(json.dumps({"results": []})))
    adapter.search(SavedSearch(query="python"), fetcher=fetcher, timeout_s=_TIMEOUT)
    # The configured country reaches the request path.
    assert fetcher.calls[0].url.startswith("https://api.adzuna.com/v1/api/jobs/gb/search/1?")
