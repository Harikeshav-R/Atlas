"""The Remotive aggregator adapter (PROJECT.md §5.4-B).

Remotive exposes a public, unauthenticated **API** at
``https://remotive.com/api/remote-jobs``: it accepts an optional ``search`` query
parameter and returns ``{"job-count": ..., "jobs": [...]}``. Each job carries
``id``, ``company_name``, ``title``, ``url`` (apply URL),
``candidate_required_location``, ``tags``, ``description`` (HTML), ``job_type``, and
``publication_date``.

The adapter passes the :class:`SavedSearch` query to the API's ``search`` parameter
(server-side keyword filtering) and then applies the shared
:func:`~atlas.discovery.aggregators.filters.matches_search` for the location /
remote filters the API does not express. It is a free / no-key source (PROJECT.md
§5.4-B), so no credentials are involved.

The fetch goes through the injected :class:`~atlas.scrape.fetcher.Fetcher`, so the
whole adapter runs offline in tests with a :class:`FakeFetcher` (AGENTS.md §6.2).
"""

from __future__ import annotations

import html
import json
from typing import TYPE_CHECKING, Any
from urllib.parse import quote_plus

from atlas.discovery.aggregators.filters import matches_search
from atlas.discovery.errors import DiscoveryError
from atlas.discovery.structure import DiscoveredPosting
from atlas.scrape.extract import extract_main_text
from atlas.scrape.structure import ScrapedPosting

if TYPE_CHECKING:
    from atlas.discovery.aggregators.structure import SavedSearch
    from atlas.scrape.fetcher import Fetcher

__all__ = ["RemotiveAdapter"]

#: Base URL of Remotive's public remote-jobs API.
_API_BASE = "https://remotive.com/api/remote-jobs"


class RemotiveAdapter:
    """Adapter for Remotive's public remote-jobs API."""

    aggregator_type = "remotive"

    def search(
        self, spec: SavedSearch, *, fetcher: Fetcher, timeout_s: int
    ) -> list[DiscoveredPosting]:
        """Fetch Remotive for ``spec`` and return the matching postings.

        Raises:
            DiscoveryError: If the response is not JSON or lacks a ``jobs`` list.
            FetchError: Propagated from the fetcher when the API can't be fetched.
        """
        url = f"{_API_BASE}?search={quote_plus(spec.query)}"
        result = fetcher(url, timeout_s=timeout_s)
        try:
            payload = json.loads(result.body)
        except json.JSONDecodeError as exc:
            raise DiscoveryError("Remotive returned a non-JSON response.") from exc
        jobs = payload.get("jobs") if isinstance(payload, dict) else None
        if not isinstance(jobs, list):
            raise DiscoveryError("Remotive returned no 'jobs' list.")
        discovered: list[DiscoveredPosting] = []
        for job in jobs:
            posting = _normalize_job(job)
            if posting is not None and matches_search(posting.posting, spec):
                discovered.append(posting)
        return discovered


def _normalize_job(job: Any) -> DiscoveredPosting | None:
    """Map one Remotive job onto a :class:`DiscoveredPosting`.

    Returns ``None`` (skipping the job) when the object is not a dict or is missing
    the fields Atlas requires — an id, a title, and an apply URL — so a single
    malformed job never fails the whole response.
    """
    if not isinstance(job, dict):
        return None
    job_id = job.get("id")
    title = job.get("title")
    apply_url = job.get("url")
    if not job_id or not title or not apply_url:
        return None
    tags = job.get("tags")
    keywords = [str(tag) for tag in tags] if isinstance(tags, list) else []
    description = extract_main_text(html.unescape(job.get("description") or ""))
    return DiscoveredPosting(
        external_id=str(job_id),
        posting=ScrapedPosting(
            title=str(title),
            company=str(job.get("company_name") or ""),
            apply_url=str(apply_url),
            location=job.get("candidate_required_location"),
            employment_type=job.get("job_type"),
            remote_type="remote",
            keywords=keywords,
            description=description,
            posted_at=job.get("publication_date"),
        ),
    )
