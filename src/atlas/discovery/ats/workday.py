"""The Workday ATS adapter (PROJECT.md §5.4-A).

Workday hosts each customer on a per-tenant, per-datacenter domain
(``<tenant>.<wdN>.myworkdayjobs.com``) and exposes its careers site through the
**CxS API** — unlike the other adapters this is a **POST** with a JSON body and
**pagination**:

``POST https://<tenant>.<wdN>.myworkdayjobs.com/wday/cxs/<tenant>/<site>/jobs``
with body ``{"appliedFacets": {}, "limit": N, "offset": M, "searchText": ""}`` and
``Accept: application/json``. Each page returns ``{"total": N, "jobPostings": [...]}``.

Because the registry stores a single ``board_ref`` string but Workday needs three
values, :meth:`detect` produces a **compound** ``"<tenant>:<wd>:<site>"`` token
that :meth:`list_postings` parses back apart.

Detection covers the public board URL and the raw CxS API URL:

- ``https://<tenant>.<wdN>.myworkdayjobs.com/<locale?>/<site>`` — the tenant is the
  first host label, the datacenter the second (a ``wd``-prefixed label), and the
  site the last path segment (a leading ``xx-XX`` locale is skipped);
- ``https://<tenant>.<wdN>.myworkdayjobs.com/wday/cxs/<tenant>/<site>/jobs`` — the
  tenant/site come from the path after ``cxs``.

**Known limitation:** the apply URL omits any locale segment; a tenant that
requires one may 404 — carrying an optional locale in ``board_ref`` is a follow-up.
"""

from __future__ import annotations

import json
import logging
import re
from typing import TYPE_CHECKING, Any
from urllib.parse import urlsplit

from atlas.discovery.errors import DiscoveryError
from atlas.discovery.structure import DiscoveredPosting
from atlas.scrape.structure import ScrapedPosting

if TYPE_CHECKING:
    from atlas.scrape.fetcher import Fetcher

__all__ = ["WorkdayAdapter"]

_LOGGER = logging.getLogger(__name__)

#: Workday's public jobs domain suffix.
_HOST_SUFFIX = ".myworkdayjobs.com"

#: A Workday datacenter host label (e.g. ``wd5``).
_DATACENTER = re.compile(r"^wd\d+$")

#: A locale path segment (e.g. ``en-US``) to skip when finding the site.
_LOCALE = re.compile(r"^[a-z]{2}-[A-Z]{2}$")

#: Postings per CxS page, and the page cap (→ ≤200 postings) to bound the poll.
_LIMIT = 20
_MAX_PAGES = 10


class WorkdayAdapter:
    """Adapter for Workday's per-tenant CxS careers API."""

    ats_type = "workday"

    def detect(self, url: str) -> str | None:
        """Return the compound ``"<tenant>:<wd>:<site>"`` token in ``url``, or ``None``.

        Pure and offline — see the module docstring for the recognized URL forms.
        """
        parts = urlsplit(url.strip())
        host = (parts.hostname or "").lower()
        if not host.endswith(_HOST_SUFFIX):
            return None
        labels = host.split(".")
        if len(labels) < 2 or not _DATACENTER.match(labels[1]):
            return None
        tenant, datacenter = labels[0], labels[1]
        segments = [segment for segment in parts.path.split("/") if segment]
        # Raw CxS API URL: .../wday/cxs/<tenant>/<site>/jobs.
        if "cxs" in segments:
            index = segments.index("cxs")
            remainder = segments[index + 1 :]
            # remainder = [<tenant>, <site>, "jobs"?]; need at least tenant + site.
            if len(remainder) < 2:
                return None
            site = remainder[1]
        else:
            # Board URL: /<locale?>/<site>; the site is the last non-empty segment.
            usable = [segment for segment in segments if not _LOCALE.match(segment)]
            if not usable:
                return None
            site = usable[-1]
        return f"{tenant}:{datacenter}:{site}"

    def list_postings(
        self, board_ref: str, *, fetcher: Fetcher, timeout_s: int
    ) -> list[DiscoveredPosting]:
        """Fetch and normalize every posting on the Workday board ``board_ref``.

        Pages through the CxS API until all postings are collected or the page cap
        is hit (logging a warning if capped, per AGENTS.md — no silent truncation).

        Raises:
            DiscoveryError: If ``board_ref`` is malformed or a page response is not
                usable JSON.
            FetchError: Propagated from the fetcher when the board can't be fetched.
        """
        tenant, datacenter, site = _parse_board_ref(board_ref)
        base = f"https://{tenant}.{datacenter}{_HOST_SUFFIX}"
        endpoint = f"{base}/wday/cxs/{tenant}/{site}/jobs"
        discovered: list[DiscoveredPosting] = []
        total = 0
        for page in range(_MAX_PAGES):
            body = {
                "appliedFacets": {},
                "limit": _LIMIT,
                "offset": page * _LIMIT,
                "searchText": "",
            }
            result = fetcher(
                endpoint,
                timeout_s=timeout_s,
                method="POST",
                json_body=body,
                headers={"Accept": "application/json"},
            )
            total, jobs = _parse_page(result.body, board_ref)
            if not jobs:
                break
            for job in jobs:
                posting = _normalize_job(job, base)
                if posting is not None:
                    discovered.append(posting)
            if len(discovered) >= total:
                break
        else:
            # Ran the full page range without collecting everything (the loop
            # breaks as soon as len >= total), so the board was capped — surface it
            # rather than silently truncating (AGENTS.md).
            _LOGGER.warning(
                "Workday board %r capped at %d of %d postings.",
                board_ref,
                len(discovered),
                total,
            )
        return discovered


def _parse_board_ref(board_ref: str) -> tuple[str, str, str]:
    """Split a compound ``"<tenant>:<wd>:<site>"`` board ref into its three parts.

    Raises:
        DiscoveryError: If ``board_ref`` is not exactly three colon-separated parts.
    """
    parts = board_ref.split(":")
    if len(parts) != 3 or not all(parts):
        raise DiscoveryError(f"Malformed Workday board reference {board_ref!r}.")
    tenant, datacenter, site = parts
    return tenant, datacenter, site


def _parse_page(raw: str, board_ref: str) -> tuple[int, list[Any]]:
    """Parse one CxS page body into ``(total, jobPostings)``.

    Raises:
        DiscoveryError: If the body is not JSON, or lacks an integer ``total`` and a
            ``jobPostings`` list.
    """
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise DiscoveryError(f"Workday board {board_ref!r} returned a non-JSON response.") from exc
    total = payload.get("total") if isinstance(payload, dict) else None
    jobs = payload.get("jobPostings") if isinstance(payload, dict) else None
    if not isinstance(total, int) or not isinstance(jobs, list):
        raise DiscoveryError(f"Workday board {board_ref!r} returned an unexpected response.")
    return total, jobs


def _normalize_job(job: Any, base: str) -> DiscoveredPosting | None:
    """Map one Workday jobPosting onto a :class:`DiscoveredPosting`.

    Returns ``None`` (skipping the posting) when the object is not a dict or has no
    ``externalPath`` (needed for both the apply URL and the external id).
    """
    if not isinstance(job, dict):
        return None
    external_path = job.get("externalPath")
    title = job.get("title")
    if not external_path or not title:
        return None
    # The JR id is the trailing "_JR123" of the external path; fall back to the
    # whole path when there is no underscore.
    external_id = str(external_path).rsplit("_", 1)[-1]
    return DiscoveredPosting(
        external_id=external_id,
        posting=ScrapedPosting(
            title=title,
            apply_url=f"{base}{external_path}",
            location=job.get("locationsText"),
            posted_at=job.get("postedOn"),
        ),
    )
