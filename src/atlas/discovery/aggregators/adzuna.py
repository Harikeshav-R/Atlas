"""The Adzuna aggregator adapter (PROJECT.md §5.4-B).

Adzuna is a **key-gated** aggregator: its public search API needs a free
``app_id`` + ``app_key`` (query-string auth). A company's jobs for a country are
searched at
``https://api.adzuna.com/v1/api/jobs/{country}/search/1?app_id=…&app_key=…&what=…``,
which returns ``{"results": [...]}``.

Unlike the free feeds, this adapter is **constructed with resolved credentials**
by :func:`atlas.discovery.aggregators.build_aggregator` (which reads the
``[aggregators.adzuna]`` config and resolves the keys from the OS keychain), so
the credentials never touch :meth:`search`'s signature and are never logged. When
the config is disabled or a key is missing the builder returns ``None`` and the
source is skipped as inactive — the key is never required to be present for Atlas
to run.

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
    from atlas.config.schema import AdzunaConfig
    from atlas.config.secrets import SecretStore
    from atlas.discovery.aggregators.structure import SavedSearch
    from atlas.scrape.fetcher import Fetcher

__all__ = ["AdzunaAdapter", "build_adzuna"]

#: Base URL of Adzuna's public search API (the country + page are appended).
_API_BASE = "https://api.adzuna.com/v1/api/jobs"

#: How many results to request per search (Adzuna's first page).
_RESULTS_PER_PAGE = 50


class AdzunaAdapter:
    """Adapter for Adzuna's key-gated public search API."""

    aggregator_type = "adzuna"
    requires_key = True

    def __init__(self, *, app_id: str, app_key: str, country: str) -> None:
        """Store the resolved credentials and the country to search."""
        self._app_id = app_id
        self._app_key = app_key
        self._country = country

    def search(
        self, spec: SavedSearch, *, fetcher: Fetcher, timeout_s: int
    ) -> list[DiscoveredPosting]:
        """Fetch Adzuna for ``spec`` and return the matching postings.

        Raises:
            DiscoveryError: If the response is not JSON or lacks a ``results`` list.
            FetchError: Propagated from the fetcher when the API can't be fetched.
        """
        params = [
            f"app_id={quote_plus(self._app_id)}",
            f"app_key={quote_plus(self._app_key)}",
            f"results_per_page={_RESULTS_PER_PAGE}",
            f"what={quote_plus(spec.query)}",
        ]
        if spec.location:
            params.append(f"where={quote_plus(spec.location)}")
        url = f"{_API_BASE}/{quote_plus(self._country)}/search/1?{'&'.join(params)}"
        result = fetcher(url, timeout_s=timeout_s)
        try:
            payload = json.loads(result.body)
        except json.JSONDecodeError as exc:
            raise DiscoveryError("Adzuna returned a non-JSON response.") from exc
        results = payload.get("results") if isinstance(payload, dict) else None
        if not isinstance(results, list):
            raise DiscoveryError("Adzuna returned no 'results' list.")
        discovered: list[DiscoveredPosting] = []
        for job in results:
            posting = _normalize_job(job)
            if posting is not None and matches_search(posting.posting, spec):
                discovered.append(posting)
        return discovered


def build_adzuna(config: AdzunaConfig, store: SecretStore) -> AdzunaAdapter | None:
    """Build an :class:`AdzunaAdapter`, or ``None`` when it can't be activated.

    Returns ``None`` when Adzuna is disabled in config or either credential is
    absent from the keychain (the source is then shown as "needs API key" and
    skipped by the poll rather than failing). Credentials are resolved from their
    configured handles and passed to the adapter directly — never logged, never
    written to the environment.
    """
    if not config.enabled:
        return None
    app_id = resolve_api_key(store, config.app_id_handle, allow_env_fallback=False)
    app_key = resolve_api_key(store, config.app_key_handle, allow_env_fallback=False)
    if not app_id or not app_key:
        return None
    return AdzunaAdapter(app_id=app_id, app_key=app_key, country=config.country)


def _normalize_job(job: Any) -> DiscoveredPosting | None:
    """Map one Adzuna result onto a :class:`DiscoveredPosting`.

    Returns ``None`` (skipping the result) when the object is not a dict or is
    missing the fields Atlas requires — an id, a title, and an apply URL
    (``redirect_url``) — so a single malformed result never fails the response.
    """
    if not isinstance(job, dict):
        return None
    job_id = job.get("id")
    title = job.get("title")
    apply_url = job.get("redirect_url")
    if not job_id or not title or not apply_url:
        return None
    company = job.get("company")
    company_name = company.get("display_name") if isinstance(company, dict) else None
    location = job.get("location")
    location_name = location.get("display_name") if isinstance(location, dict) else None
    description = extract_main_text(html.unescape(job.get("description") or ""))
    return DiscoveredPosting(
        external_id=str(job_id),
        posting=ScrapedPosting(
            title=str(title),
            company=str(company_name or ""),
            apply_url=str(apply_url),
            location=location_name,
            description=description,
            posted_at=job.get("created"),
        ),
    )
