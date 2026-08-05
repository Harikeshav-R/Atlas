"""Tests for the pure watchlist/discovery display logic in :mod:`atlas.cli.discovery`.

Exercised against the in-memory ``db_engine`` fixture and plain models, without
invoking the CLI (AGENTS.md §6.2).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from atlas.cli.console import console
from atlas.cli.discovery import (
    build_watchlist_report,
    render_discovery_outcome,
    render_watchlist,
)
from atlas.db import session_scope
from atlas.discovery.poller import DiscoveryOutcome
from atlas.discovery.repository import get_or_create_ats_source, stamp_last_polled_at
from atlas.scrape.repository import get_or_create_company

if TYPE_CHECKING:
    from rich.console import RenderableType
    from sqlalchemy.engine import Engine

_POLLED = datetime(2026, 8, 4, 9, 0, tzinfo=UTC)


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
