"""The USAJOBS aggregator adapter (PROJECT.md §5.4-B).

USAJOBS (the US federal government's job board) exposes a public search API that
uses **header auth**: a free API key sent as ``Authorization-Key`` plus the
registering email as the ``User-Agent``. Jobs are searched at
``https://data.usajobs.gov/api/search?Keyword=…``, returning a nested
``{"SearchResult": {"SearchResultItems": [{"MatchedObjectId", "MatchedObjectDescriptor":
{…}}]}}``.

This is the reason the shared :class:`~atlas.scrape.fetcher.Fetcher` seam carries a
``headers`` parameter — USAJOBS cannot pass its credential in the query string the
way Adzuna does. Like Adzuna, the adapter is **constructed with resolved
credentials** by :func:`atlas.discovery.aggregators.build_aggregator` (which reads
``[aggregators.usajobs]`` and resolves the key from the OS keychain), so the key
never touches :meth:`search`'s signature and is never logged. When disabled, or
missing the key or the email, the builder returns ``None`` and the source is
skipped as inactive.

The fetch goes through the injected :class:`~atlas.scrape.fetcher.Fetcher`, so the
whole adapter runs offline in tests with a :class:`FakeFetcher` (AGENTS.md §6.2).
"""

from __future__ import annotations

import html
import json
from typing import TYPE_CHECKING, Any
from urllib.parse import quote_plus

from atlas.config.secrets import resolve_api_key
from atlas.discovery.aggregators.filters import matches_search
from atlas.discovery.errors import DiscoveryError
from atlas.discovery.structure import DiscoveredPosting
from atlas.scrape.extract import extract_main_text
from atlas.scrape.structure import ScrapedPosting

if TYPE_CHECKING:
    from atlas.config.schema import UsajobsConfig
    from atlas.config.secrets import SecretStore
    from atlas.discovery.aggregators.structure import SavedSearch
    from atlas.scrape.fetcher import Fetcher

__all__ = ["UsajobsAdapter", "build_usajobs"]

#: USAJOBS's public search endpoint.
_API_URL = "https://data.usajobs.gov/api/search"

#: The API host, sent as the ``Host`` header USAJOBS expects.
_API_HOST = "data.usajobs.gov"


class UsajobsAdapter:
    """Adapter for the USAJOBS key-gated public search API (header auth)."""

    aggregator_type = "usajobs"
    requires_key = True

    def __init__(self, *, email: str, api_key: str) -> None:
        """Store the resolved credentials (email → User-Agent, api key → header)."""
        self._email = email
        self._api_key = api_key

    def search(
        self, spec: SavedSearch, *, fetcher: Fetcher, timeout_s: int
    ) -> list[DiscoveredPosting]:
        """Fetch USAJOBS for ``spec`` and return the matching postings.

        Raises:
            DiscoveryError: If the response is not JSON or lacks the expected
                ``SearchResult.SearchResultItems`` list.
            FetchError: Propagated from the fetcher when the API can't be fetched.
        """
        params = [f"Keyword={quote_plus(spec.query)}"]
        if spec.location:
            params.append(f"LocationName={quote_plus(spec.location)}")
        url = f"{_API_URL}?{'&'.join(params)}"
        headers = {
            "Host": _API_HOST,
            "User-Agent": self._email,
            "Authorization-Key": self._api_key,
        }
        result = fetcher(url, timeout_s=timeout_s, headers=headers)
        try:
            payload = json.loads(result.body)
        except json.JSONDecodeError as exc:
            raise DiscoveryError("USAJOBS returned a non-JSON response.") from exc
        search_result = payload.get("SearchResult") if isinstance(payload, dict) else None
        items = search_result.get("SearchResultItems") if isinstance(search_result, dict) else None
        if not isinstance(items, list):
            raise DiscoveryError("USAJOBS returned no 'SearchResultItems' list.")
        discovered: list[DiscoveredPosting] = []
        for item in items:
            posting = _normalize_item(item)
            if posting is not None and matches_search(posting.posting, spec):
                discovered.append(posting)
        return discovered


def build_usajobs(config: UsajobsConfig, store: SecretStore) -> UsajobsAdapter | None:
    """Build a :class:`UsajobsAdapter`, or ``None`` when it can't be activated.

    Returns ``None`` when USAJOBS is disabled, no email is configured, or the API
    key is absent from the keychain (the source is then shown as "needs API key"
    and skipped rather than failing). The key is resolved from its configured
    handle and passed to the adapter directly — never logged or put in the
    environment.
    """
    if not config.enabled or not config.email:
        return None
    api_key = resolve_api_key(store, config.api_key_handle, allow_env_fallback=False)
    if not api_key:
        return None
    return UsajobsAdapter(email=config.email, api_key=api_key)


def _normalize_item(item: Any) -> DiscoveredPosting | None:
    """Map one USAJOBS search-result item onto a :class:`DiscoveredPosting`.

    Returns ``None`` (skipping the item) when the object is not a dict, lacks a
    descriptor, or is missing the fields Atlas requires — an id, a title, and an
    apply URL — so a single malformed item never fails the response.
    """
    if not isinstance(item, dict):
        return None
    descriptor = item.get("MatchedObjectDescriptor")
    if not isinstance(descriptor, dict):
        return None
    external_id = item.get("MatchedObjectId")
    title = descriptor.get("PositionTitle")
    apply_url = descriptor.get("PositionURI") or descriptor.get("ApplyURI")
    if isinstance(apply_url, list):
        # ApplyURI is sometimes a list of URLs; take the first (or drop if empty).
        apply_url = apply_url[0] if apply_url else None
    if not external_id or not title or not apply_url:
        return None
    summary = ""
    user_area = descriptor.get("UserArea")
    if isinstance(user_area, dict):
        details = user_area.get("Details")
        if isinstance(details, dict):
            summary = extract_main_text(html.unescape(str(details.get("JobSummary") or "")))
    return DiscoveredPosting(
        external_id=str(external_id),
        posting=ScrapedPosting(
            title=str(title),
            company=str(descriptor.get("OrganizationName") or ""),
            apply_url=str(apply_url),
            location=descriptor.get("PositionLocationDisplay"),
            description=summary,
            posted_at=descriptor.get("PublicationStartDate"),
        ),
    )
