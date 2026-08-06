"""The daemon's scheduled discovery poll (PROJECT.md §4.1, §5.4).

The discovery counterpart to :mod:`atlas.daemon.poll`'s scoring poll, written as a
**pure function over an open** :class:`~sqlmodel.Session` (like the service layer)
so it is tested directly with the in-memory ``db_engine`` fixture and a
:class:`FakeFetcher`, with no scheduler or process in the loop (AGENTS.md §6.2).

For each enabled ATS source it resolves the provider's adapter, lists the board's
postings through the injected fetcher, and persists the new ones (dedup handled by
:func:`~atlas.discovery.service.persist_discovered`), then stamps
``last_polled_at``. Polling is **best-effort per source**: a source that can't be
polled (an unknown provider, an unusable board response, or a fetch failure) is
counted and skipped rather than aborting the batch — mirroring
:func:`atlas.daemon.poll.run_scoring_poll`'s handling of a `MatchingError`. The
scoring poll then picks up the newly-inserted unscored postings on its own pass.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from pydantic import BaseModel

from atlas.daemon.progress import ProgressUpdate, emit_progress
from atlas.discovery.aggregators import build_aggregator
from atlas.discovery.aggregators.structure import SavedSearch
from atlas.discovery.ats import get_adapter
from atlas.discovery.errors import DiscoveryError
from atlas.discovery.repository import (
    list_enabled_aggregator_sources,
    list_enabled_ats_sources,
    stamp_last_polled_at,
)
from atlas.discovery.service import persist_aggregated, persist_discovered
from atlas.resume.service import utcnow
from atlas.scrape.errors import FetchError
from atlas.scrape.fetcher import default_fetcher

if TYPE_CHECKING:
    from collections.abc import Callable
    from datetime import datetime

    from sqlmodel import Session

    from atlas.config.schema import AggregatorsConfig
    from atlas.config.secrets import SecretStore
    from atlas.daemon.progress import ProgressCallback
    from atlas.scrape.fetcher import Fetcher

__all__ = ["DiscoveryOutcome", "run_aggregator_poll", "run_discovery_poll"]

_LOGGER = logging.getLogger(__name__)

#: Per-board-fetch timeout in seconds (matches the scrape service's default).
_TIMEOUT_S = 30


class DiscoveryOutcome(BaseModel):
    """The result of one discovery poll.

    Attributes:
        sources_polled: How many enabled sources were polled successfully.
        discovered: How many new postings were inserted across all sources.
        skipped: How many discovered postings were duplicates and skipped.
        failed_sources: How many sources could not be polled (unknown provider,
            unusable response, or fetch failure) and were left for a later run.
        inactive: How many enabled sources were skipped because they are not yet
            usable — a key-gated aggregator whose credential is not configured.
            Reported (never silently dropped) but distinct from a failure. Always
            ``0`` for the ATS poll, which has no key-gated sources.
    """

    sources_polled: int
    discovered: int
    skipped: int
    failed_sources: int
    inactive: int = 0


def run_discovery_poll(
    session: Session,
    *,
    fetcher: Fetcher = default_fetcher,
    clock: Callable[[], datetime] = utcnow,
    on_progress: ProgressCallback | None = None,
) -> DiscoveryOutcome:
    """Poll every enabled ATS source and persist newly-discovered postings.

    Args:
        session: The open session/transaction to work within.
        fetcher: The HTTP boundary the adapters fetch boards through (injectable
            for tests).
        clock: The clock for ``fetched_at`` / ``last_polled_at`` (injectable).
        on_progress: Optional sink for progress updates (:mod:`atlas.daemon.progress`).
            ``None`` (the default) leaves every existing caller unaffected. A
            ``start`` update carries the source count; an ``item`` update fires per
            source (whether polled or failed); a ``done`` update closes the poll.

    Returns:
        A :class:`DiscoveryOutcome` summarizing the poll.
    """
    sources_polled = 0
    discovered = 0
    skipped = 0
    failed_sources = 0
    sources = list(list_enabled_ats_sources(session))
    emit_progress(on_progress, ProgressUpdate(stage="start", total=len(sources)))
    for index, source in enumerate(sources, start=1):
        ats_type = str(source.config.get("ats_type", ""))
        board_token = str(source.config.get("board_token", ""))
        company_id = int(source.config["company_id"])
        try:
            adapter = get_adapter(ats_type)
            postings = adapter.list_postings(board_token, fetcher=fetcher, timeout_s=_TIMEOUT_S)
            outcome = persist_discovered(
                session,
                source=source,
                company_id=company_id,
                discovered=postings,
                clock=clock,
            )
        except (DiscoveryError, FetchError):
            # Unknown provider / unusable board / fetch failure — skip this source
            # best-effort rather than aborting the whole poll.
            _LOGGER.warning("Discovery poll skipped a source (type=%s).", ats_type)
            failed_sources += 1
        else:
            stamp_last_polled_at(session, source, clock())
            sources_polled += 1
            discovered += outcome.discovered
            skipped += outcome.skipped
        emit_progress(
            on_progress,
            ProgressUpdate(
                stage="item",
                label=f"{ats_type}:{board_token}",
                done=index,
                total=len(sources),
            ),
        )
    emit_progress(
        on_progress,
        ProgressUpdate(stage="done", done=len(sources), total=len(sources)),
    )
    return DiscoveryOutcome(
        sources_polled=sources_polled,
        discovered=discovered,
        skipped=skipped,
        failed_sources=failed_sources,
    )


def run_aggregator_poll(
    session: Session,
    *,
    config: AggregatorsConfig,
    store: SecretStore,
    fetcher: Fetcher = default_fetcher,
    clock: Callable[[], datetime] = utcnow,
    on_progress: ProgressCallback | None = None,
) -> DiscoveryOutcome:
    """Poll every enabled aggregator saved search and persist new postings.

    The aggregator counterpart to :func:`run_discovery_poll`: for each enabled
    aggregator source it **builds** the provider's adapter (resolving any key-gated
    credentials from ``store`` via ``config``), rebuilds the saved search from the
    source config, runs it through the injected fetcher, and persists the new
    postings (dedup + per-posting company handled by
    :func:`~atlas.discovery.service.persist_aggregated`), then stamps
    ``last_polled_at``.

    A key-gated provider that is disabled or missing its credential builds to
    ``None`` and is skipped as **inactive** — reported in ``DiscoveryOutcome.inactive``
    (so the user learns a source needs a key), distinct from a failure. Polling is
    otherwise **best-effort per source** — an unknown provider, an unusable response,
    or a fetch failure is counted in ``failed_sources`` and skipped rather than
    aborting the batch.

    Args:
        session: The open session/transaction to work within.
        config: The ``[aggregators]`` settings (enable flags + key handles).
        store: The secret store key-gated adapters resolve their credentials from.
        fetcher: The HTTP boundary the adapters fetch through (injectable for tests).
        clock: The clock for ``fetched_at`` / ``last_polled_at`` (injectable).
        on_progress: Optional sink for progress updates (:mod:`atlas.daemon.progress`).
            ``None`` (the default) leaves every existing caller unaffected. A
            ``start`` update carries the source count; an ``item`` update fires per
            source (polled, inactive, or failed alike); a ``done`` update closes it.

    Returns:
        A :class:`DiscoveryOutcome` summarizing the poll.
    """
    sources_polled = 0
    discovered = 0
    skipped = 0
    failed_sources = 0
    inactive = 0
    sources = list(list_enabled_aggregator_sources(session))
    emit_progress(on_progress, ProgressUpdate(stage="start", total=len(sources)))
    for index, source in enumerate(sources, start=1):
        aggregator = str(source.config.get("aggregator", ""))
        try:
            adapter = build_aggregator(aggregator, config=config, store=store)
            if adapter is None:
                # Key-gated + unconfigured/keyless — inactive, not a failure.
                _LOGGER.info("Aggregator source needs an API key (aggregator=%s).", aggregator)
                inactive += 1
            else:
                spec = SavedSearch.model_validate(source.config.get("search", {}))
                postings = adapter.search(spec, fetcher=fetcher, timeout_s=_TIMEOUT_S)
                outcome = persist_aggregated(
                    session,
                    source=source,
                    discovered=postings,
                    clock=clock,
                )
                stamp_last_polled_at(session, source, clock())
                sources_polled += 1
                discovered += outcome.discovered
                skipped += outcome.skipped
        except (DiscoveryError, FetchError):
            # Unknown provider / unusable response / fetch failure — skip this source
            # best-effort rather than aborting the whole poll.
            _LOGGER.warning("Aggregator poll skipped a source (aggregator=%s).", aggregator)
            failed_sources += 1
        emit_progress(
            on_progress,
            ProgressUpdate(
                stage="item",
                label=aggregator,
                done=index,
                total=len(sources),
            ),
        )
    emit_progress(
        on_progress,
        ProgressUpdate(stage="done", done=len(sources), total=len(sources)),
    )
    return DiscoveryOutcome(
        sources_polled=sources_polled,
        discovered=discovered,
        skipped=skipped,
        failed_sources=failed_sources,
        inactive=inactive,
    )
