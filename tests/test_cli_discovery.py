"""Tests for the pure watchlist/discovery display logic in :mod:`atlas.cli.discovery`.

Exercised against the in-memory ``db_engine`` fixture and plain models, without
invoking the CLI (AGENTS.md §6.2).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from atlas.cli.console import console
from atlas.cli.discovery import (
    build_saved_search_report,
    build_watchlist_report,
    render_discovery_outcome,
    render_saved_searches,
    render_watchlist,
)
from atlas.db import session_scope
from atlas.discovery.aggregators.structure import SavedSearch
from atlas.discovery.poller import DiscoveryOutcome
from atlas.discovery.repository import (
    get_or_create_aggregator_source,
    get_or_create_ats_source,
    stamp_last_polled_at,
)
from atlas.profiles.preferences import ProfilePreferences
from atlas.profiles.repository import create_profile
from atlas.scrape.repository import get_or_create_company

if TYPE_CHECKING:
    from rich.console import RenderableType
    from sqlalchemy.engine import Engine

_POLLED = datetime(2026, 8, 4, 9, 0, tzinfo=UTC)


def _profile(engine: Engine) -> int:
    with session_scope(engine) as session:
        profile = create_profile(session, name="Backend", preferences=ProfilePreferences())
        assert profile.id is not None
        return profile.id


def _render(renderable: RenderableType) -> str:
    with console.capture() as capture:
        console.print(renderable)
    return capture.get()


def test_build_watchlist_report_maps_sources(db_engine: Engine) -> None:
    with session_scope(db_engine) as session:
        company = get_or_create_company(session, name="Acme")
        assert company.id is not None
        source = get_or_create_ats_source(
            session, ats_type="greenhouse", board_token="acme", company_id=company.id
        )
        stamp_last_polled_at(session, source, _POLLED)
    with session_scope(db_engine) as session:
        report = build_watchlist_report(session)
    assert len(report.entries) == 1
    entry = report.entries[0]
    assert entry.company == "Acme"
    assert entry.ats_type == "greenhouse"
    assert entry.board_token == "acme"
    assert entry.enabled is True
    assert entry.last_polled_at == _POLLED


def test_render_watchlist_empty_hint(db_engine: Engine) -> None:
    with session_scope(db_engine) as session:
        report = build_watchlist_report(session)
    text = _render(render_watchlist(report))
    assert "atlas company add" in text


def test_render_watchlist_table(db_engine: Engine) -> None:
    with session_scope(db_engine) as session:
        company = get_or_create_company(session, name="Acme")
        assert company.id is not None
        # A never-polled, disabled board exercises the "never" + "no" branches.
        source = get_or_create_ats_source(
            session, ats_type="greenhouse", board_token="acme", company_id=company.id
        )
        source.enabled = False
        session.add(source)
        session.flush()
    with session_scope(db_engine) as session:
        report = build_watchlist_report(session)
    text = _render(render_watchlist(report))
    assert "Acme" in text
    assert "greenhouse" in text
    assert "never" in text
    assert "no" in text


def test_render_discovery_outcome_no_failures() -> None:
    text = _render(
        render_discovery_outcome(
            DiscoveryOutcome(sources_polled=1, discovered=3, skipped=1, failed_sources=0)
        )
    )
    assert "Discovered" in text
    assert "3" in text


def test_render_discovery_outcome_with_failures() -> None:
    text = _render(
        render_discovery_outcome(
            DiscoveryOutcome(sources_polled=0, discovered=0, skipped=0, failed_sources=2)
        )
    )
    assert "Failed sources" in text
    assert "2" in text


def test_render_discovery_outcome_with_inactive() -> None:
    text = _render(
        render_discovery_outcome(
            DiscoveryOutcome(
                sources_polled=0, discovered=0, skipped=0, failed_sources=0, inactive=1
            )
        )
    )
    assert "Needs API key" in text
    assert "atlas source key" in text


def test_build_saved_search_report_maps_sources(db_engine: Engine) -> None:
    profile_id = _profile(db_engine)
    with session_scope(db_engine) as session:
        source = get_or_create_aggregator_source(
            session,
            aggregator="remoteok",
            spec=SavedSearch(query="python", location="remote"),
            profile_id=profile_id,
        )
        stamp_last_polled_at(session, source, _POLLED)
    with session_scope(db_engine) as session:
        report = build_saved_search_report(session)
    assert len(report.entries) == 1
    entry = report.entries[0]
    assert entry.aggregator == "remoteok"
    assert entry.query == "python"
    assert entry.location == "remote"
    assert entry.profile == "Backend"
    assert entry.enabled is True
    assert entry.last_polled_at == _POLLED


def test_render_saved_searches_empty_hint(db_engine: Engine) -> None:
    with session_scope(db_engine) as session:
        report = build_saved_search_report(session)
    text = _render(render_saved_searches(report))
    assert "atlas source add" in text


def test_render_saved_searches_table(db_engine: Engine) -> None:
    from atlas.db.models import JobSource

    profile_id = _profile(db_engine)
    with session_scope(db_engine) as session:
        # A polled, enabled search with a real profile (covers profile-resolved).
        polled = get_or_create_aggregator_source(
            session,
            aggregator="remoteok",
            spec=SavedSearch(query="python"),
            profile_id=profile_id,
        )
        stamp_last_polled_at(session, polled, _POLLED)
        # A never-polled, disabled, no-location, no-profile search exercises the
        # "never" / "no" / "any" / "—" (unresolved profile) branches.
        session.add(
            JobSource(
                type="aggregator",
                config={"aggregator": "remotive", "search": {"query": "rust"}},
                profile_id=None,
                enabled=False,
            )
        )
        session.flush()
    with session_scope(db_engine) as session:
        report = build_saved_search_report(session)
    text = _render(render_saved_searches(report))
    assert "remoteok" in text
    assert "remotive" in text
    assert "rust" in text
    assert "never" in text
    assert "any" in text
