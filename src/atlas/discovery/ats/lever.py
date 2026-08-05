"""The Lever ATS adapter (PROJECT.md §5.4-A).

Lever exposes a public, unauthenticated **Postings API**: a company's board is
identified by a *site* token and its published postings are listed at
``https://api.lever.co/v0/postings/{site}?mode=json``, which returns a **raw JSON
array** of postings (not a wrapped object).

Detection is a pure, offline URL classifier covering both the public board URL and
the raw API URL the user might paste:

- ``https://jobs.lever.co/<site>`` (and the EU host ``jobs.eu.lever.co``) — the
  site is the first path segment;
- ``https://api.lever.co/v0/postings/<site>`` (and ``api.eu.lever.co``) — the site
  is the segment after ``postings``.

The listing fetch goes through the injected :class:`~atlas.scrape.fetcher.Fetcher`
so the whole adapter runs offline in tests with a :class:`FakeFetcher` (AGENTS.md
§6.2).

**Known limitation:** ``list_postings`` always polls the US base (``api.lever.co``).
An EU-only board added via an ``eu`` URL still watchlists (``detect`` returns the
bare site token) but may 404 on poll; encoding the region in ``board_ref`` is a
follow-up.
"""

from __future__ import annotations

import html
import json
from typing import TYPE_CHECKING, Any
from urllib.parse import urlsplit

from atlas.discovery.errors import DiscoveryError
from atlas.discovery.structure import DiscoveredPosting
from atlas.scrape.extract import extract_main_text
from atlas.scrape.structure import ScrapedPosting

if TYPE_CHECKING:
    from atlas.scrape.fetcher import Fetcher

__all__ = ["LeverAdapter"]

#: Base URL of Lever's public Postings API (US).
_API_BASE = "https://api.lever.co/v0/postings"

#: Public board hosts (US + EU); the site is the first path segment.
_BOARD_HOSTS = frozenset({"jobs.lever.co", "jobs.eu.lever.co"})

#: API hosts (US + EU); the site is the path segment after ``postings``.
_API_HOSTS = frozenset({"api.lever.co", "api.eu.lever.co"})


class LeverAdapter:
    """Adapter for Lever's public Postings API."""

    ats_type = "lever"

    def detect(self, url: str) -> str | None:
        """Return the Lever site token in ``url``, or ``None``.

        Pure and offline — see the module docstring for the recognized URL forms.
        """
        parts = urlsplit(url.strip())
        host = (parts.hostname or "").lower()
        segments = [segment for segment in parts.path.split("/") if segment]
        if host in _BOARD_HOSTS:
            return segments[0] if segments else None
        if host in _API_HOSTS:
            # .../v0/postings/<site>: the token follows the "postings" segment.
            if "postings" in segments:
                index = segments.index("postings")
                remainder = segments[index + 1 :]
                return remainder[0] if remainder else None
            return None
        return None

    def list_postings(
        self, board_ref: str, *, fetcher: Fetcher, timeout_s: int
    ) -> list[DiscoveredPosting]:
        """Fetch and normalize every posting on the Lever board ``board_ref``.

        Raises:
            DiscoveryError: If the response is not JSON or is not a list.
            FetchError: Propagated from the fetcher when the board can't be fetched.
        """
        url = f"{_API_BASE}/{board_ref}?mode=json"
        result = fetcher(url, timeout_s=timeout_s)
        try:
            payload = json.loads(result.body)
        except json.JSONDecodeError as exc:
            raise DiscoveryError(
                f"Lever board {board_ref!r} returned a non-JSON response."
            ) from exc
        if not isinstance(payload, list):
            raise DiscoveryError(f"Lever board {board_ref!r} did not return a postings list.")
        discovered: list[DiscoveredPosting] = []
        for job in payload:
            posting = _normalize_job(job)
            if posting is not None:
                discovered.append(posting)
        return discovered


def _normalize_job(job: Any) -> DiscoveredPosting | None:
    """Map one Lever posting onto a :class:`DiscoveredPosting`.

    Returns ``None`` (skipping the posting) when the object is not a dict or is
    missing the fields Atlas requires — an id, a title (``text``), and an apply
    URL — so a single malformed posting never fails the whole board.
    """
    if not isinstance(job, dict):
        return None
    job_id = job.get("id")
    title = job.get("text")
    apply_url = job.get("hostedUrl") or job.get("applyUrl")
    if not job_id or not title or not apply_url:
        return None
    categories = job.get("categories")
    if not isinstance(categories, dict):
        categories = {}
    plain = job.get("descriptionPlain")
    description = plain if plain else extract_main_text(html.unescape(job.get("description") or ""))
    posted_at = job.get("createdAt")
    return DiscoveredPosting(
        external_id=str(job_id),
        posting=ScrapedPosting(
            title=title,
            apply_url=apply_url,
            location=categories.get("location"),
            employment_type=categories.get("commitment"),
            team=categories.get("team"),
            remote_type=job.get("workplaceType"),
            description=description,
            posted_at=str(posted_at) if posted_at is not None else None,
        ),
    )
