"""The Greenhouse ATS adapter (PROJECT.md §5.4-A).

Greenhouse exposes a public, unauthenticated **Job Board API**: a company's board
is identified by a *board token* and its jobs are listed at
``https://boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true``. With
``content=true`` each job carries its full HTML description (as HTML entities), its
apply URL, and its location, which is everything the fit-scoring pipeline needs.

Detection is a pure, offline URL classifier covering the board-URL forms a user is
likely to paste:

- ``https://boards.greenhouse.io/<token>`` and the newer
  ``https://job-boards.greenhouse.io/<token>`` — the first path segment is the
  token;
- ``https://boards.greenhouse.io/embed/job_board?for=<token>`` — the embedded
  board, whose token is the ``for`` query parameter;
- ``https://<token>.greenhouse.io`` — the per-company subdomain form.

The listing fetch goes through the injected
:class:`~atlas.scrape.fetcher.Fetcher`, so the whole adapter is exercised offline
with a :class:`FakeFetcher` replaying a recorded board payload (AGENTS.md §6.2).
"""

from __future__ import annotations

import html
import json
from typing import TYPE_CHECKING, Any
from urllib.parse import parse_qs, urlsplit

from atlas.discovery.errors import DiscoveryError
from atlas.discovery.structure import DiscoveredPosting
from atlas.scrape.extract import extract_main_text
from atlas.scrape.structure import ScrapedPosting

if TYPE_CHECKING:
    from atlas.scrape.fetcher import Fetcher

__all__ = ["GreenhouseAdapter"]

#: Base URL of Greenhouse's public Job Board API.
_API_BASE = "https://boards-api.greenhouse.io/v1/boards"

#: Hosts that carry a board token in their first path segment.
_BOARD_HOSTS = frozenset({"boards.greenhouse.io", "job-boards.greenhouse.io"})

#: First path segments that are Greenhouse routes, not board tokens.
_RESERVED_SEGMENTS = frozenset({"embed", "job_board"})

#: Subdomain labels that are Greenhouse infrastructure, not company tokens, in the
#: ``<token>.greenhouse.io`` form.
_RESERVED_SUBDOMAINS = frozenset({"boards", "job-boards", "api", "www"})


class GreenhouseAdapter:
    """Adapter for Greenhouse's public Job Board API."""

    ats_type = "greenhouse"

    def detect(self, url: str) -> str | None:
        """Return the Greenhouse board token in ``url``, or ``None``.

        Pure and offline — see the module docstring for the recognized URL forms.
        """
        parts = urlsplit(url.strip())
        host = (parts.hostname or "").lower()
        if not host.endswith("greenhouse.io"):
            return None
        segments = [segment for segment in parts.path.split("/") if segment]
        if host in _BOARD_HOSTS:
            # Embedded board: .../embed/job_board?for=<token>.
            if segments[:2] == ["embed", "job_board"]:
                for_values = parse_qs(parts.query).get("for")
                return for_values[0] if for_values else None
            # Plain board: /<token>/...; ignore reserved routes.
            if segments and segments[0] not in _RESERVED_SEGMENTS:
                return segments[0]
            return None
        # Per-company subdomain: <token>.greenhouse.io.
        label = host.split(".")[0]
        if label in _RESERVED_SUBDOMAINS:
            return None
        return label

    def list_postings(
        self, board_ref: str, *, fetcher: Fetcher, timeout_s: int
    ) -> list[DiscoveredPosting]:
        """Fetch and normalize every posting on the Greenhouse board ``board_ref``.

        Raises:
            DiscoveryError: If the response is not JSON or lacks a ``jobs`` array.
            FetchError: Propagated from the fetcher when the board can't be fetched.
        """
        url = f"{_API_BASE}/{board_ref}/jobs?content=true"
        result = fetcher(url, timeout_s=timeout_s)
        try:
            payload = json.loads(result.body)
        except json.JSONDecodeError as exc:
            raise DiscoveryError(
                f"Greenhouse board {board_ref!r} returned a non-JSON response."
            ) from exc
        jobs = payload.get("jobs") if isinstance(payload, dict) else None
        if not isinstance(jobs, list):
            raise DiscoveryError(f"Greenhouse board {board_ref!r} returned no 'jobs' list.")
        discovered: list[DiscoveredPosting] = []
        for job in jobs:
            posting = _normalize_job(job)
            if posting is not None:
                discovered.append(posting)
        return discovered


def _normalize_job(job: Any) -> DiscoveredPosting | None:
    """Map one Greenhouse job object onto a :class:`DiscoveredPosting`.

    Returns ``None`` (skipping the job) when the object is not a dict or is missing
    the fields Atlas requires — an id, a title, and an apply URL — so a single
    malformed job never fails the whole board.
    """
    if not isinstance(job, dict):
        return None
    job_id = job.get("id")
    title = job.get("title")
    apply_url = job.get("absolute_url")
    if job_id is None or not title or not apply_url:
        return None
    location = job.get("location")
    location_name = location.get("name") if isinstance(location, dict) else None
    content = job.get("content")
    description = extract_main_text(html.unescape(content)) if content else ""
    posted_at = job.get("updated_at")
    return DiscoveredPosting(
        external_id=str(job_id),
        posting=ScrapedPosting(
            title=title,
            apply_url=apply_url,
            location=location_name,
            description=description,
            posted_at=posted_at,
        ),
    )
