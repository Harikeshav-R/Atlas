"""Job discovery from structured ATS boards (PROJECT.md §4.1, §5.4).

The daemon's discovery half: a company **watchlist** of ATS boards and the
per-provider **adapters** that turn each board's public listing into normalized,
persisted :class:`~atlas.db.models.JobPosting` rows. Ships the **Greenhouse**
adapter today, behind an extensible :class:`~atlas.discovery.ats.base.AtsAdapter`
interface + registry (:mod:`atlas.discovery.ats`) so Lever/Ashby/Workday drop in
as later PRs.

Everything is written as pure logic over an injected fetcher and open session
(like :mod:`atlas.scrape`), so the discovery poll (:mod:`atlas.discovery.poller`)
runs offline in tests with a fake fetcher and the in-memory DB (AGENTS.md §6.2).
"""

from __future__ import annotations

from atlas.discovery.ats import ATS_TYPES, AtsAdapter, detect_ats, get_adapter
from atlas.discovery.errors import DiscoveryError, UnknownAtsError
from atlas.discovery.structure import DiscoveredPosting

__all__ = [
    "ATS_TYPES",
    "AtsAdapter",
    "DiscoveredPosting",
    "DiscoveryError",
    "UnknownAtsError",
    "detect_ats",
    "get_adapter",
]
