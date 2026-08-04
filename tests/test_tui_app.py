"""Async ``Pilot``-driven tests for the Atlas TUI (:mod:`atlas.tui`).

These are the project's first async tests (``asyncio_mode = "auto"``). Each drives
:class:`~atlas.tui.app.AtlasApp` through Textual's ``App.run_test()`` harness over
the in-memory ``db_engine`` fixture, exercising screen composition, navigation, the
table/Kanban toggle, and status changes (valid + invalid). The autouse
``reset_atlas_logging`` fixture restores logging/terminal state if a run aborts.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from textual.widgets import DataTable, OptionList

from atlas.db import session_scope
from atlas.matching.repository import create_match_score
from atlas.profiles.preferences import ProfilePreferences
from atlas.profiles.repository import create_profile
from atlas.scrape.repository import (
    create_job_posting,
    get_or_create_company,
    get_or_create_url_source,
)
from atlas.tailor.repository import get_or_create_application
from atlas.tracking.service import set_application_status
from atlas.tracking.status import ApplicationStatus
from atlas.tui.app import AtlasApp
from atlas.tui.screens.application_detail import ApplicationDetailScreen
from atlas.tui.screens.applications import ApplicationsScreen
from atlas.tui.screens.dashboard import DashboardScreen
from atlas.tui.screens.posting_detail import PostingDetailScreen
from atlas.tui.screens.status_picker import StatusPickerScreen

if TYPE_CHECKING:
    from sqlalchemy.engine import Engine

_NOW = datetime(2026, 8, 4, 9, 30, tzinfo=UTC)


def _seed(engine: Engine, *, scored: bool = True) -> int:
    """Seed a posting + profile + application; return the application id."""
    with session_scope(engine) as session:
        company = get_or_create_company(session, name="Acme")
        source = get_or_create_url_source(session)
        assert company.id is not None
        assert source.id is not None
        posting = create_job_posting(
            session,
            source_id=source.id,
            company_id=company.id,
            title="Backend Engineer",
            apply_url="https://jobs.acme.test/1",
            dedupe_hash="h",
            fetched_at=_NOW,
            location="Remote",
            keywords=["python"],
            description="Build things.",
        )
        profile = create_profile(session, name="BE", preferences=ProfilePreferences(), active=True)
        assert posting.id is not None
        assert profile.id is not None
        if scored:
            create_match_score(
                session,
                job_posting_id=posting.id,
                profile_id=profile.id,
                score=82,
                verdict="strong",
                rationale="Great fit.",
                matched_strengths=[],
                gaps=[],
                dealbreaker_hits=[],
                salary_fit="within",
                signals={},
                model="fake",
                created_at=_NOW,
            )
        application = get_or_create_application(
            session, job_posting_id=posting.id, profile_id=profile.id, clock=_NOW
        )
        assert application.id is not None
        return application.id


async def test_dashboard_mounts_with_data(db_engine: Engine) -> None:
    _seed(db_engine)
    async with AtlasApp(engine=db_engine).run_test() as pilot:
        await pilot.pause()
        assert isinstance(pilot.app.screen, DashboardScreen)
        funnel = pilot.app.screen.query_one("#funnel", DataTable)
        assert funnel.row_count == len(ApplicationStatus)


async def test_dashboard_empty(db_engine: Engine) -> None:
    async with AtlasApp(engine=db_engine).run_test() as pilot:
        await pilot.pause()
        recent = pilot.app.screen.query_one("#recent", DataTable)
        assert recent.row_count == 0


async def test_dashboard_shows_deadline(db_engine: Engine) -> None:
    app_id = _seed(db_engine)
    due = datetime(2026, 8, 20, tzinfo=UTC)
    with session_scope(db_engine) as session:
        set_application_status(session, app_id, ApplicationStatus.READY, clock=lambda: _NOW)
    with session_scope(db_engine) as session:
        set_application_status(
            session, app_id, ApplicationStatus.APPLIED, due=due, clock=lambda: _NOW
        )
    async with AtlasApp(engine=db_engine).run_test() as pilot:
        await pilot.pause()
        deadlines = pilot.app.screen.query_one("#deadlines", DataTable)
        assert deadlines.row_count == 1


async def test_navigate_dashboard_to_applications_and_back(db_engine: Engine) -> None:
    _seed(db_engine)
    async with AtlasApp(engine=db_engine).run_test() as pilot:
        await pilot.pause()
        await pilot.press("a")
        await pilot.pause()
        assert isinstance(pilot.app.screen, ApplicationsScreen)
        await pilot.press("d")
        await pilot.pause()
        assert isinstance(pilot.app.screen, DashboardScreen)


async def test_applications_table_and_kanban_toggle(db_engine: Engine) -> None:
    _seed(db_engine)
    async with AtlasApp(engine=db_engine).run_test() as pilot:
        await pilot.pause()
        await pilot.press("a")
        await pilot.pause()
        screen = pilot.app.screen
        assert isinstance(screen, ApplicationsScreen)
        table = screen.query_one("#apps-table", DataTable)
        assert bool(table.display) is True
        assert table.row_count == 1
        await pilot.press("k")  # to Kanban
        await pilot.pause()
        assert bool(table.display) is False
        await pilot.press("k")  # back to table
        await pilot.pause()
        assert bool(table.display) is True


async def test_open_application_detail_and_posting(db_engine: Engine) -> None:
    _seed(db_engine)
    async with AtlasApp(engine=db_engine).run_test() as pilot:
        await pilot.pause()
        await pilot.press("a")
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        assert isinstance(pilot.app.screen, ApplicationDetailScreen)
        await pilot.press("p")
        await pilot.pause()
        assert isinstance(pilot.app.screen, PostingDetailScreen)
        await pilot.press("escape")
        await pilot.pause()
        assert isinstance(pilot.app.screen, ApplicationDetailScreen)


async def test_open_detail_noop_when_empty(db_engine: Engine) -> None:
    async with AtlasApp(engine=db_engine).run_test() as pilot:
        await pilot.pause()
        await pilot.press("a")
        await pilot.pause()
        await pilot.press("enter")  # empty table → no detail pushed
        await pilot.pause()
        assert isinstance(pilot.app.screen, ApplicationsScreen)


async def test_status_change_valid_from_applications(db_engine: Engine) -> None:
    app_id = _seed(db_engine)
    async with AtlasApp(engine=db_engine).run_test() as pilot:
        await pilot.pause()
        await pilot.press("a")
        await pilot.pause()
        await pilot.press("s")  # open the status picker
        await pilot.pause()
        assert isinstance(pilot.app.screen, StatusPickerScreen)
        # Select "ready" (a valid move from preparing).
        picker = pilot.app.screen.query_one(OptionList)
        picker.highlighted = list(ApplicationStatus).index(ApplicationStatus.READY)
        await pilot.press("enter")
        await pilot.pause()
        assert isinstance(pilot.app.screen, ApplicationsScreen)
    # The change persisted.
    from atlas.tui.data import build_application_detail

    with session_scope(db_engine) as session:
        assert build_application_detail(session, app_id).status == "ready"


async def test_status_change_invalid_shows_error(db_engine: Engine) -> None:
    app_id = _seed(db_engine)
    async with AtlasApp(engine=db_engine).run_test() as pilot:
        await pilot.pause()
        await pilot.press("a")
        await pilot.pause()
        await pilot.press("s")
        await pilot.pause()
        picker = pilot.app.screen.query_one(OptionList)
        picker.highlighted = list(ApplicationStatus).index(ApplicationStatus.OFFER)
        await pilot.press("enter")  # preparing → offer is illegal
        await pilot.pause()
        assert isinstance(pilot.app.screen, ApplicationsScreen)
    # Status is unchanged.
    from atlas.tui.data import build_application_detail

    with session_scope(db_engine) as session:
        assert build_application_detail(session, app_id).status == "preparing"


async def test_status_picker_cancel(db_engine: Engine) -> None:
    _seed(db_engine)
    async with AtlasApp(engine=db_engine).run_test() as pilot:
        await pilot.pause()
        await pilot.press("a")
        await pilot.pause()
        await pilot.press("s")
        await pilot.pause()
        assert isinstance(pilot.app.screen, StatusPickerScreen)
        await pilot.press("escape")  # cancel → back to applications, no change
        await pilot.pause()
        assert isinstance(pilot.app.screen, ApplicationsScreen)


async def test_set_status_noop_when_empty(db_engine: Engine) -> None:
    async with AtlasApp(engine=db_engine).run_test() as pilot:
        await pilot.pause()
        await pilot.press("a")
        await pilot.pause()
        await pilot.press("s")  # empty table → no picker
        await pilot.pause()
        assert isinstance(pilot.app.screen, ApplicationsScreen)


async def test_status_change_from_detail(db_engine: Engine) -> None:
    app_id = _seed(db_engine)
    async with AtlasApp(engine=db_engine).run_test() as pilot:
        await pilot.pause()
        await pilot.press("a")
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        assert isinstance(pilot.app.screen, ApplicationDetailScreen)
        await pilot.press("s")
        await pilot.pause()
        picker = pilot.app.screen.query_one(OptionList)
        picker.highlighted = list(ApplicationStatus).index(ApplicationStatus.READY)
        await pilot.press("enter")
        await pilot.pause()
        assert isinstance(pilot.app.screen, ApplicationDetailScreen)
        timeline = pilot.app.screen.query_one("#timeline", DataTable)
        assert timeline.row_count == 1

    from atlas.tui.data import build_application_detail

    with session_scope(db_engine) as session:
        assert build_application_detail(session, app_id).status == "ready"


async def test_detail_status_picker_cancel(db_engine: Engine) -> None:
    app_id = _seed(db_engine)
    async with AtlasApp(engine=db_engine).run_test() as pilot:
        await pilot.pause()
        await pilot.press("a")
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        await pilot.press("s")
        await pilot.pause()
        assert isinstance(pilot.app.screen, StatusPickerScreen)
        await pilot.press("escape")  # cancel → back to detail, no change
        await pilot.pause()
        assert isinstance(pilot.app.screen, ApplicationDetailScreen)

    from atlas.tui.data import build_application_detail

    with session_scope(db_engine) as session:
        assert build_application_detail(session, app_id).status == "preparing"


async def test_detail_invalid_status_shows_error(db_engine: Engine) -> None:
    app_id = _seed(db_engine)
    async with AtlasApp(engine=db_engine).run_test() as pilot:
        await pilot.pause()
        await pilot.press("a")
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        await pilot.press("s")
        await pilot.pause()
        picker = pilot.app.screen.query_one(OptionList)
        picker.highlighted = list(ApplicationStatus).index(ApplicationStatus.OFFER)
        await pilot.press("enter")  # illegal from preparing
        await pilot.pause()
        assert isinstance(pilot.app.screen, ApplicationDetailScreen)

    from atlas.tui.data import build_application_detail

    with session_scope(db_engine) as session:
        assert build_application_detail(session, app_id).status == "preparing"
