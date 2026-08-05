"""The RemoteOK aggregator adapter (PROJECT.md §5.4-B).

RemoteOK exposes a public, unauthenticated **JSON feed** at
``https://remoteok.com/api``: a **raw JSON array** whose *first element* is a legal
/ metadata notice object (not a job), followed by one object per posting. Each job
carries ``id`` / ``slug``, ``company``, ``position`` (the title), ``location``,
``tags``, ``description`` (HTML), ``url`` (apply URL), and ``date``.

RemoteOK has no server-side query parameter on the public feed, so the adapter
fetches the whole feed and **filters in code** to the :class:`SavedSearch`'s query
(matched against the title / tags / description) and optional location. It is a
free / no-key source (PROJECT.md §5.4-B), so no credentials are involved.

The fetch goes through the injected :class:`~atlas.scrape.fetcher.Fetcher`, so the
whole adapter runs offline in tests with a :class:`FakeFetcher` (AGENTS.md §6.2).
"""

from __future__ import annotations

import html
import json
from typing import TYPE_CHECKING, Any

from atlas.discovery.aggregators.filters import matches_search
from atlas.discovery.errors import DiscoveryError
from atlas.discovery.structure import DiscoveredPosting
from atlas.scrape.extract import extract_main_text
from atlas.scrape.structure import ScrapedPosting

if TYPE_CHECKING:
    from atlas.discovery.aggregators.structure import SavedSearch
    from atlas.scrape.fetcher import Fetcher

__all__ = ["RemoteOKAdapter"]

#: RemoteOK's public JSON feed.
_API_URL = "https://remoteok.com/api"


class RemoteOKAdapter:
    """Adapter for RemoteOK's public JSON feed."""

    aggregator_type = "remoteok"
    requires_key = False

    def search(
        self, spec: SavedSearch, *, fetcher: Fetcher, timeout_s: int
    ) -> list[DiscoveredPosting]:
        """Fetch the RemoteOK feed and return postings matching ``spec``.

        Raises:
            DiscoveryError: If the response is not JSON or is not a list.
            FetchError: Propagated from the fetcher when the feed can't be fetched.
        """
        result = fetcher(_API_URL, timeout_s=timeout_s)
        try:
            payload = json.loads(result.body)
        except json.JSONDecodeError as exc:
            raise DiscoveryError("RemoteOK returned a non-JSON response.") from exc
        if not isinstance(payload, list):
            raise DiscoveryError("RemoteOK did not return a postings list.")
        discovered: list[DiscoveredPosting] = []
        for job in payload:
            posting = _normalize_job(job)
            if posting is not None and matches_search(posting.posting, spec):
                discovered.append(posting)
        return discovered


def _normalize_job(job: Any) -> DiscoveredPosting | None:
    """Map one RemoteOK feed entry onto a :class:`DiscoveredPosting`.

    Returns ``None`` (skipping the entry) when the object is not a dict — which
    also skips the feed's leading legal/metadata notice — or is missing the fields
    Atlas requires: an id, a title (``position``), and an apply URL (``url``). So a
    single malformed entry or the notice never fails the whole feed.
    """
    if not isinstance(job, dict):
        return None
    job_id = job.get("id") or job.get("slug")
    title = job.get("position")
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
            company=str(job.get("company") or ""),
            apply_url=str(apply_url),
            location=job.get("location"),
            remote_type="remote",
            keywords=keywords,
            description=description,
            posted_at=job.get("date"),
        ),
    )
