"""Watchlist reporting and discovery rendering for the Atlas CLI.

The ``atlas company`` and ``atlas discover`` commands (PROJECT.md §9) keep their
Typer wiring thin in :mod:`atlas.cli.main` and delegate here, mirroring the
``atlas postings`` split (:mod:`atlas.cli.scrape`): this module holds the **pure,
I/O-light logic** — building a serializable view of the watchlisted ATS boards and
rendering the watchlist and a poll outcome through the shared semantic theme — so
it is testable against the in-memory ``db_engine`` fixture without invoking the CLI
(AGENTS.md §6.2). The persistence/orchestration lives in
:mod:`atlas.discovery.service` and :mod:`atlas.discovery.poller`.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from pydantic import BaseModel
from rich.table import Table
from rich.text import Text
from sqlmodel import col, select

from atlas.db.models import Company, JobSource
from atlas.discovery.repository import AGGREGATOR_SOURCE_TYPE, ATS_SOURCE_TYPE

if TYPE_CHECKING:
    from rich.console import RenderableType
    from sqlmodel import Session

    from atlas.discovery.poller import DiscoveryOutcome

__all__ = [
    "SavedSearchEntry",
    "SavedSearchReport",
    "WatchlistEntry",
    "WatchlistReport",
    "build_saved_search_report",
    "build_watchlist_report",
    "render_discovery_outcome",
    "render_saved_searches",
    "render_watchlist",
]


class WatchlistEntry(BaseModel):
    """A compact, serializable view of one watchlisted ATS board.

    Attributes:
        source_id: The ATS :class:`~atlas.db.models.JobSource`'s id.
        company: The company's display name.
        ats_type: The ATS provider (e.g. ``"greenhouse"``).
        board_token: The board token on that ATS.
        enabled: Whether the discovery poll includes this board.
        last_polled_at: When the board was last polled, or ``None`` if never.
    """

    source_id: int
    company: str
    ats_type: str
    board_token: str
    enabled: bool
    last_polled_at: datetime | None = None


class WatchlistReport(BaseModel):
    """The result of ``atlas company list``.

    Attributes:
        entries: One :class:`WatchlistEntry` per watchlisted ATS board, in
            insertion order.
    """

    entries: list[WatchlistEntry]


def build_watchlist_report(session: Session) -> WatchlistReport:
    """Build a :class:`WatchlistReport` from every ATS source.

    Pure over the session: reads the ``type="ats"`` sources and maps each into a
    :class:`WatchlistEntry`, resolving the owning company's name for display.
    """
    entries: list[WatchlistEntry] = []
    sources = session.exec(
        select(JobSource).where(JobSource.type == ATS_SOURCE_TYPE).order_by(col(JobSource.id))
    ).all()
    for source in sources:
        assert source.id is not None  # persisted rows always have an id
        company = session.get(Company, int(source.config["company_id"]))
        # The source config always references an existing company (set on add).
        assert company is not None
        entries.append(
            WatchlistEntry(
                source_id=source.id,
                company=company.name,
                ats_type=str(source.config.get("ats_type", "")),
                board_token=str(source.config.get("board_token", "")),
                enabled=source.enabled,
                last_polled_at=source.last_polled_at,
            )
        )
    return WatchlistReport(entries=entries)


def render_watchlist(report: WatchlistReport) -> RenderableType:
    """Render a :class:`WatchlistReport` as a styled Rich renderable.

    Produces a table of watchlisted boards (company, ATS, board token, enabled,
    last polled) using the shared semantic theme. An empty report renders a muted
    hint pointing at ``atlas company add``.
    """
    if not report.entries:
        return Text("No companies watchlisted — run `atlas company add <url>`.", style="muted")
    table = Table(title="Watchlist", title_style="heading", title_justify="left")
    table.add_column("ID", justify="right", no_wrap=True)
    table.add_column("Company", style="accent")
    table.add_column("ATS")
    table.add_column("Board")
    table.add_column("Enabled", no_wrap=True)
    table.add_column("Last polled", style="muted")
    for entry in report.entries:
        table.add_row(
            str(entry.source_id),
            entry.company,
            entry.ats_type,
            entry.board_token,
            Text("yes", style="success") if entry.enabled else Text("no", style="muted"),
            entry.last_polled_at.isoformat() if entry.last_polled_at is not None else "never",
        )
    return table


def render_discovery_outcome(outcome: DiscoveryOutcome) -> RenderableType:
    """Render a :class:`~atlas.discovery.poller.DiscoveryOutcome` as a Rich grid."""
    grid = Table.grid(padding=(0, 2))
    grid.add_column(style="muted", no_wrap=True)
    grid.add_column()
    grid.add_row("Sources polled", str(outcome.sources_polled))
    grid.add_row("Discovered", Text(str(outcome.discovered), style="success"))
    grid.add_row("Skipped (duplicates)", str(outcome.skipped))
    failed_style = "error" if outcome.failed_sources else "muted"
    grid.add_row("Failed sources", Text(str(outcome.failed_sources), style=failed_style))
    if outcome.inactive:
        grid.add_row(
            "Needs API key",
            Text(f"{outcome.inactive} (run atlas source key)", style="warning"),
        )
    return grid


class SavedSearchEntry(BaseModel):
    """A compact, serializable view of one aggregator saved search.

    Attributes:
        source_id: The aggregator :class:`~atlas.db.models.JobSource`'s id.
        aggregator: The aggregator provider (e.g. ``"remoteok"``).
        query: The search's query text.
        location: The search's location filter, if any.
        profile: The owning profile's display name, or ``None`` if unresolved.
        enabled: Whether the discovery poll includes this search.
        last_polled_at: When the search was last polled, or ``None`` if never.
    """

    source_id: int
    aggregator: str
    query: str
    location: str | None = None
    profile: str | None = None
    enabled: bool
    last_polled_at: datetime | None = None


class SavedSearchReport(BaseModel):
    """The result of ``atlas source list``.

    Attributes:
        entries: One :class:`SavedSearchEntry` per aggregator saved search, in
            insertion order.
    """

    entries: list[SavedSearchEntry]


def build_saved_search_report(session: Session) -> SavedSearchReport:
    """Build a :class:`SavedSearchReport` from every aggregator source.

    Pure over the session: reads the ``type="aggregator"`` sources and maps each
    into a :class:`SavedSearchEntry`, resolving the owning profile's name for
    display when set.
    """
    from atlas.db.models import Profile

    entries: list[SavedSearchEntry] = []
    sources = session.exec(
        select(JobSource)
        .where(JobSource.type == AGGREGATOR_SOURCE_TYPE)
        .order_by(col(JobSource.id))
    ).all()
    for source in sources:
        assert source.id is not None  # persisted rows always have an id
        search = source.config.get("search", {})
        profile_name: str | None = None
        if source.profile_id is not None:
            profile = session.get(Profile, source.profile_id)
            profile_name = profile.name if profile is not None else None
        entries.append(
            SavedSearchEntry(
                source_id=source.id,
                aggregator=str(source.config.get("aggregator", "")),
                query=str(search.get("query", "")),
                location=search.get("location"),
                profile=profile_name,
                enabled=source.enabled,
                last_polled_at=source.last_polled_at,
            )
        )
    return SavedSearchReport(entries=entries)


def render_saved_searches(report: SavedSearchReport) -> RenderableType:
    """Render a :class:`SavedSearchReport` as a styled Rich renderable.

    Produces a table of saved searches (aggregator, query, location, profile,
    enabled, last polled) using the shared semantic theme. An empty report renders
    a muted hint pointing at ``atlas source add``.
    """
    if not report.entries:
        return Text(
            "No saved searches — run `atlas source add <aggregator> --query ...`.",
            style="muted",
        )
    table = Table(title="Saved searches", title_style="heading", title_justify="left")
    table.add_column("ID", justify="right", no_wrap=True)
    table.add_column("Aggregator", style="accent")
    table.add_column("Query")
    table.add_column("Location")
    table.add_column("Profile", style="muted")
    table.add_column("Enabled", no_wrap=True)
    table.add_column("Last polled", style="muted")
    for entry in report.entries:
        table.add_row(
            str(entry.source_id),
            entry.aggregator,
            entry.query,
            entry.location or "any",
            entry.profile or "—",
            Text("yes", style="success") if entry.enabled else Text("no", style="muted"),
            entry.last_polled_at.isoformat() if entry.last_polled_at is not None else "never",
        )
    return table
