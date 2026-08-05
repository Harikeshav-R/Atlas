"""The Ashby ATS adapter (PROJECT.md §5.4-A).

Ashby exposes a public, unauthenticated **Job Posting API**: an organization's
board is identified by a *job board name* and its published postings are listed at
``https://api.ashbyhq.com/posting-api/job-board/{name}``, returning
``{"apiVersion": ..., "jobs": [...]}``.

Detection is a pure, offline URL classifier covering both the public board URL and
the raw API URL the user might paste:

- ``https://jobs.ashbyhq.com/<name>`` — the name is the first path segment;
- ``https://api.ashbyhq.com/posting-api/job-board/<name>`` — the name is the
  segment after ``job-board``.

Ashby job objects carry **no top-level id**, so the external id is derived from the
job's ``jobUrl`` (its last path segment is a UUID), falling back to ``applyUrl``.
Unlisted postings (``isListed`` false) are skipped. The listing fetch goes through
the injected :class:`~atlas.scrape.fetcher.Fetcher`, so the whole adapter runs
offline in tests (AGENTS.md §6.2).
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

__all__ = ["AshbyAdapter"]

#: Base URL of Ashby's public Job Posting API.
_API_BASE = "https://api.ashbyhq.com/posting-api/job-board"

#: The public board host; the name is the first path segment.
_BOARD_HOST = "jobs.ashbyhq.com"

#: The API host; the name is the path segment after ``job-board``.
_API_HOST = "api.ashbyhq.com"


class AshbyAdapter:
    """Adapter for Ashby's public Job Posting API."""

    ats_type = "ashby"

    def detect(self, url: str) -> str | None:
        """Return the Ashby job-board name in ``url``, or ``None``.

        Pure and offline — see the module docstring for the recognized URL forms.
        """
        parts = urlsplit(url.strip())
        host = (parts.hostname or "").lower()
        segments = [segment for segment in parts.path.split("/") if segment]
        if host == _BOARD_HOST:
            return segments[0] if segments else None
        if host == _API_HOST:
            # .../posting-api/job-board/<name>: the name follows "job-board".
            if "job-board" in segments:
                index = segments.index("job-board")
                remainder = segments[index + 1 :]
                return remainder[0] if remainder else None
            return None
        return None

    def list_postings(
        self, board_ref: str, *, fetcher: Fetcher, timeout_s: int
    ) -> list[DiscoveredPosting]:
        """Fetch and normalize every listed posting on the Ashby board ``board_ref``.

        Raises:
            DiscoveryError: If the response is not JSON or lacks a ``jobs`` list.
            FetchError: Propagated from the fetcher when the board can't be fetched.
        """
        url = f"{_API_BASE}/{board_ref}?includeCompensation=false"
        result = fetcher(url, timeout_s=timeout_s)
        try:
            payload = json.loads(result.body)
        except json.JSONDecodeError as exc:
            raise DiscoveryError(
                f"Ashby board {board_ref!r} returned a non-JSON response."
            ) from exc
        jobs = payload.get("jobs") if isinstance(payload, dict) else None
        if not isinstance(jobs, list):
            raise DiscoveryError(f"Ashby board {board_ref!r} returned no 'jobs' list.")
        discovered: list[DiscoveredPosting] = []
        for job in jobs:
            posting = _normalize_job(job)
            if posting is not None:
                discovered.append(posting)
        return discovered


def _external_id(job: dict[str, Any]) -> str | None:
    """Derive a stable external id from a job's ``jobUrl`` (else ``applyUrl``).

    Ashby jobs have no top-level id; the ``jobUrl``'s last path segment is a UUID.
    Returns ``None`` when neither URL yields a non-empty segment.
    """
    for key in ("jobUrl", "applyUrl"):
        raw = job.get(key)
        if not raw:
            continue
        segment = urlsplit(str(raw)).path.rstrip("/").rsplit("/", 1)[-1]
        if segment:
            return segment
    return None


def _normalize_job(job: Any) -> DiscoveredPosting | None:
    """Map one Ashby job onto a :class:`DiscoveredPosting`.

    Returns ``None`` (skipping the job) when the object is not a dict, is unlisted
    (``isListed`` is ``False``), has no derivable external id, or is missing a
    title or an apply URL — so a single malformed/unlisted job never fails the
    board.
    """
    if not isinstance(job, dict):
        return None
    if job.get("isListed") is False:
        return None
    external_id = _external_id(job)
    title = job.get("title")
    apply_url = job.get("applyUrl") or job.get("jobUrl")
    if external_id is None or not title or not apply_url:
        return None
    plain = job.get("descriptionPlain")
    description = (
        plain if plain else extract_main_text(html.unescape(job.get("descriptionHtml") or ""))
    )
    return DiscoveredPosting(
        external_id=external_id,
        posting=ScrapedPosting(
            title=title,
            apply_url=apply_url,
            location=job.get("location"),
            employment_type=job.get("employmentType"),
            remote_type=job.get("workplaceType"),
            description=description,
            posted_at=job.get("publishedAt"),
        ),
    )
