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
from atlas.discovery.poller import DiscoveryOutcome, run_discovery_poll
from atlas.discovery.repository import (
    ATS_SOURCE_TYPE,
    get_ats_source,
    get_or_create_ats_source,
    get_posting_by_source_external,
    list_enabled_ats_sources,
    stamp_last_polled_at,
)
from atlas.discovery.service import (
    AddCompanyOutcome,
    PersistOutcome,
    add_watchlist_company,
    persist_discovered,
)
from atlas.discovery.structure import DiscoveredPosting

__all__ = [
    "ATS_SOURCE_TYPE",
    "ATS_TYPES",
    "AddCompanyOutcome",
    "AtsAdapter",
    "DiscoveredPosting",
    "DiscoveryError",
    "DiscoveryOutcome",
    "PersistOutcome",
    "UnknownAtsError",
    "add_watchlist_company",
    "detect_ats",
    "get_adapter",
    "get_ats_source",
    "get_or_create_ats_source",
    "get_posting_by_source_external",
    "list_enabled_ats_sources",
    "persist_discovered",
    "run_discovery_poll",
    "stamp_last_polled_at",
]
