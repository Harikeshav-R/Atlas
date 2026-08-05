"""Async ``Pilot``-driven tests for the Atlas TUI (:mod:`atlas.tui`).

These are the project's first async tests (``asyncio_mode = "auto"``). Each drives
:class:`~atlas.tui.app.AtlasApp` through Textual's ``App.run_test()`` harness over
the in-memory ``db_engine`` fixture, exercising screen composition, navigation, the
table/Kanban toggle, and status changes (valid + invalid). The autouse
``reset_atlas_logging`` fixture restores logging/terminal state if a run aborts.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, cast

from textual.widgets import DataTable, Label, OptionList

from atlas.config.schema import RenderConfig, TailoringConfig
from atlas.db import session_scope
from atlas.matching.repository import create_match_score
from atlas.profiles.preferences import ProfilePreferences
from atlas.profiles.repository import create_profile, get_active_profile, upsert_user
from atlas.resume.repository import create_version
from atlas.resume.structure import BlockType, ParsedBlock, ParsedResume
from atlas.scrape.repository import (
    create_job_posting,
    get_or_create_company,
    get_or_create_url_source,
)
from atlas.tailor.repository import get_latest_tailored_resume, get_or_create_application
from atlas.tracking.service import set_application_status
from atlas.tracking.status import ApplicationStatus
from atlas.tui.app import AtlasApp
from atlas.tui.screens.application_detail import ApplicationDetailScreen
from atlas.tui.screens.applications import ApplicationsScreen
from atlas.tui.screens.dashboard import DashboardScreen
from atlas.tui.screens.discover import DiscoverScreen
from atlas.tui.screens.posting_detail import PostingDetailScreen
from atlas.tui.screens.profile_picker import ProfilePickerScreen
from atlas.tui.screens.status_picker import StatusPickerScreen
from atlas.tui.screens.tailor_workspace import TailorWorkspaceScreen
from tests.conftest import (
    FakeFileOpener,
    FakeLLMProvider,
    FakePdfRenderer,
    FakeUrlOpener,
    make_response,
)

if TYPE_CHECKING:
    from pathlib import Path

    from sqlalchemy.engine import Engine

_NOW = datetime(2026, 8, 4, 9, 30, tzinfo=UTC)

_TAILORED: dict[str, object] = {
    "items": [
        {
            "content_id": "blk_a",
            "block_type": "experience",
            "final_text": "Led the platform team",
            "reason": "core",
            "included": True,
        }
    ],
    "gaps": ["Kubernetes"],
    "summary_rationale": "focus",
}
_COVER: dict[str, object] = {
    "greeting": "Dear team",
    "hook": "I build platforms.",
    "body_paragraphs": ["Para one."],
    "closing": "Thanks",
    "gaps": [],
}


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


# --- Tailor workspace ------------------------------------------------------------


def _seed_full(engine: Engine) -> int:
    """Seed a posting + active profile + master resume + application; return app id."""
    app_id = _seed(engine, scored=False)
    with session_scope(engine) as session:
        upsert_user(session, name="Sam Lee")
        parsed = ParsedResume(
            blocks=[
                ParsedBlock(
                    type=BlockType.EXPERIENCE,
                    content_id="blk_a",
                    position=0,
                    text="Led the platform team Jan 2024 - Present",
                )
            ]
        )
        create_version(
            session, raw_markdown="# Sam", source_path=None, parsed=parsed, created_at=_NOW
        )
    return app_id


def _action_app(
    engine: Engine,
    *,
    provider: FakeLLMProvider,
    opener: FakeFileOpener | None = None,
    url_opener: FakeUrlOpener | None = None,
    renders_dir: Path | None = None,
) -> AtlasApp:
    """Build an action-capable AtlasApp with injected fakes (hermetic)."""
    return AtlasApp(
        engine=engine,
        provider=provider,
        renderer=FakePdfRenderer(),
        opener=opener if opener is not None else FakeFileOpener(),
        url_opener=url_opener if url_opener is not None else FakeUrlOpener(),
        tailoring=TailoringConfig(),
        render_config=RenderConfig(),
        renders_dir=renders_dir,
    )


async def test_workspace_opens_from_application_detail(db_engine: Engine) -> None:
    _seed_full(db_engine)
    provider = FakeLLMProvider([make_response(structured=_TAILORED)])
    async with _action_app(db_engine, provider=provider).run_test() as pilot:
        await pilot.pause()
        await pilot.press("a")
        await pilot.pause()
        await pilot.press("enter")  # → application detail
        await pilot.pause()
        await pilot.press("t")  # → tailor workspace
        await pilot.pause()
        assert isinstance(pilot.app.screen, TailorWorkspaceScreen)
        blocks = pilot.app.screen.query_one("#master-blocks", DataTable)
        assert blocks.row_count == 1


async def test_workspace_tailor_worker_persists(db_engine: Engine, tmp_path: Path) -> None:
    app_id = _seed_full(db_engine)
    provider = FakeLLMProvider([make_response(structured=_TAILORED)])
    app = _action_app(db_engine, provider=provider, renders_dir=tmp_path)
    async with app.run_test() as pilot:
        await app.push_screen(TailorWorkspaceScreen(app_id))
        await pilot.pause()
        await pilot.press("t")
        await app.workers.wait_for_complete()
        await pilot.pause()
    with session_scope(db_engine) as session:
        tailored = get_latest_tailored_resume(session, app_id)
        assert tailored is not None
        assert tailored.version == 1


async def test_workspace_cover_rerender_open(db_engine: Engine, tmp_path: Path) -> None:
    app_id = _seed_full(db_engine)
    # Tailor first (so materials exist to re-render/open), then cover.
    provider = FakeLLMProvider(
        [make_response(structured=_TAILORED), make_response(structured=_COVER)]
    )
    opener = FakeFileOpener()
    app = _action_app(db_engine, provider=provider, opener=opener, renders_dir=tmp_path)
    async with app.run_test() as pilot:
        await app.push_screen(TailorWorkspaceScreen(app_id))
        await pilot.pause()
        await pilot.press("t")  # tailor
        await app.workers.wait_for_complete()
        await pilot.pause()
        await pilot.press("c")  # cover letter
        await app.workers.wait_for_complete()
        await pilot.pause()
        await pilot.press("r")  # re-render (no AI)
        await app.workers.wait_for_complete()
        await pilot.pause()
        await pilot.press("o")  # open
        await app.workers.wait_for_complete()
        await pilot.pause()
    assert len(opener.opened) >= 1  # at least the resume PDF was opened


async def test_workspace_worker_error_is_handled(db_engine: Engine, tmp_path: Path) -> None:
    # No active profile → tailor_posting raises NoActiveProfileError inside the worker.
    app_id = _seed(db_engine, scored=False)
    with session_scope(db_engine) as session:
        active = get_active_profile(session)
        assert active is not None
        active.active = False  # deactivate so tailoring has no profile to target
        session.add(active)
    provider = FakeLLMProvider([make_response(structured=_TAILORED)])
    app = _action_app(db_engine, provider=provider, renders_dir=tmp_path)
    async with app.run_test() as pilot:
        await app.push_screen(TailorWorkspaceScreen(app_id))
        await pilot.pause()
        await pilot.press("t")
        await app.workers.wait_for_complete()
        await pilot.pause()
        # The app survived the worker error and stayed on the workspace.
        assert isinstance(pilot.app.screen, TailorWorkspaceScreen)
    with session_scope(db_engine) as session:
        assert get_latest_tailored_resume(session, app_id) is None  # nothing persisted


async def test_workspace_browse_only_disables_actions(db_engine: Engine) -> None:
    app_id = _seed_full(db_engine)
    # No provider/renderer → browse-only.
    async with AtlasApp(engine=db_engine).run_test() as pilot:
        await pilot.pause()
        await pilot.app.push_screen(TailorWorkspaceScreen(app_id))
        await pilot.pause()
        assert not cast(AtlasApp, pilot.app).actions_enabled
        # Every AI/render action is disabled (no worker, no crash).
        for key in ("t", "c", "r"):
            await pilot.press(key)
            await pilot.pause()
            assert isinstance(pilot.app.screen, TailorWorkspaceScreen)
    with session_scope(db_engine) as session:
        assert get_latest_tailored_resume(session, app_id) is None


async def test_workspace_open_with_no_materials(db_engine: Engine, tmp_path: Path) -> None:
    # The open action has no actions_enabled guard; with nothing rendered it opens
    # nothing and runs cleanly.
    app_id = _seed_full(db_engine)
    provider = FakeLLMProvider([])
    opener = FakeFileOpener()
    app = _action_app(db_engine, provider=provider, opener=opener, renders_dir=tmp_path)
    async with app.run_test() as pilot:
        await app.push_screen(TailorWorkspaceScreen(app_id))
        await pilot.pause()
        await pilot.press("o")  # open with nothing rendered yet
        await app.workers.wait_for_complete()
        await pilot.pause()
        assert isinstance(pilot.app.screen, TailorWorkspaceScreen)
    assert opener.opened == []  # no materials → nothing opened


# --- Discover screen ------------------------------------------------------------


def _seed_scored_posting(
    engine: Engine, *, score: int = 82, dedupe: str = "d1", title: str = "Backend Engineer"
) -> int:
    """Seed a scored posting (no application) + an active profile; return posting id."""
    with session_scope(engine) as session:
        company = get_or_create_company(session, name="Acme")
        source = get_or_create_url_source(session)
        assert company.id is not None
        assert source.id is not None
        posting = create_job_posting(
            session,
            source_id=source.id,
            company_id=company.id,
            title=title,
            apply_url=f"https://jobs.acme.test/{dedupe}",
            dedupe_hash=dedupe,
            fetched_at=_NOW,
            location="Remote",
            salary={"min": 150000, "currency": "USD"},
        )
        assert posting.id is not None
        profile = get_active_profile(session)
        if profile is None:
            profile = create_profile(
                session, name="BE", preferences=ProfilePreferences(), active=True
            )
        assert profile.id is not None
        create_match_score(
            session,
            job_posting_id=posting.id,
            profile_id=profile.id,
            score=score,
            verdict="strong",
            rationale=f"Great fit {dedupe}.",
            matched_strengths=[],
            gaps=[],
            dealbreaker_hits=[],
            salary_fit="within",
            signals={},
            model="fake",
            created_at=_NOW,
        )
        return posting.id


async def test_discover_mounts_and_lists_scored(db_engine: Engine) -> None:
    _seed_scored_posting(db_engine, score=90, dedupe="d1")
    _seed_scored_posting(db_engine, score=70, dedupe="d2")
    async with AtlasApp(engine=db_engine).run_test() as pilot:
        await pilot.pause()
        await pilot.press("w")
        await pilot.pause()
        assert isinstance(pilot.app.screen, DiscoverScreen)
        table = pilot.app.screen.query_one("#discover-table", DataTable)
        assert table.row_count == 2
        # Highlighting the first row shows its rationale in the detail pane.
        rationale = pilot.app.screen.query_one("#discover-rationale", Label)
        assert "Great fit" in str(rationale.content)


async def test_discover_empty_queue(db_engine: Engine) -> None:
    async with AtlasApp(engine=db_engine).run_test() as pilot:
        await pilot.pause()
        await pilot.press("w")
        await pilot.pause()
        screen = pilot.app.screen
        assert isinstance(screen, DiscoverScreen)
        assert screen.query_one("#discover-table", DataTable).row_count == 0
        # Empty queue shows the hint; dismiss/save/open/enter and the profile
        # switcher (no profiles) are safe no-ops.
        for key in ("x", "s", "o", "enter", "p"):
            await pilot.press(key)
            await pilot.pause()
        assert isinstance(pilot.app.screen, DiscoverScreen)


async def test_discover_switch_profile_reranks_queue(db_engine: Engine) -> None:
    # Two profiles, each with its own scored posting. Discover shows the active
    # profile's; pressing `p` and picking the other switches + re-ranks the queue.
    backend_posting = _seed_scored_posting(db_engine, dedupe="be", title="Backend Role")
    with session_scope(db_engine) as session:
        ml = create_profile(session, name="ML", preferences=ProfilePreferences(), active=True)
        assert ml.id is not None
        ml_id = ml.id
    ml_posting = _seed_scored_posting(db_engine, dedupe="ml", title="ML Role")
    async with AtlasApp(engine=db_engine).run_test() as pilot:
        await pilot.pause()
        await pilot.press("w")
        await pilot.pause()
        screen = pilot.app.screen
        assert isinstance(screen, DiscoverScreen)
        # ML is the active profile → its posting is the only queue row.
        assert screen.query_one("#discover-table", DataTable).row_count == 1
        assert screen._posting_ids == [ml_posting]
        # Open the profile picker and choose the Backend profile (first option).
        await pilot.press("p")
        await pilot.pause()
        assert isinstance(pilot.app.screen, ProfilePickerScreen)
        picker = pilot.app.screen.query_one(OptionList)
        picker.highlighted = 0  # Backend (creation order)
        await pilot.press("enter")
        await pilot.pause()
        # Back on Discover, re-ranked to the Backend profile's posting.
        discover = pilot.app.screen
        assert isinstance(discover, DiscoverScreen)
        assert discover._posting_ids == [backend_posting]
    # The active profile actually switched (persisted).
    with session_scope(db_engine) as session:
        active = get_active_profile(session)
        assert active is not None and active.name == "BE"
        assert active.id != ml_id


async def test_discover_switch_profile_cancel_keeps_queue(db_engine: Engine) -> None:
    # Cancelling the picker (Escape) leaves the active profile and queue unchanged.
    _seed_scored_posting(db_engine, dedupe="be")
    async with AtlasApp(engine=db_engine).run_test() as pilot:
        await pilot.pause()
        await pilot.press("w")
        await pilot.pause()
        await pilot.press("p")
        await pilot.pause()
        assert isinstance(pilot.app.screen, ProfilePickerScreen)
        await pilot.press("escape")
        await pilot.pause()
        assert isinstance(pilot.app.screen, DiscoverScreen)
        assert pilot.app.screen.query_one("#discover-table", DataTable).row_count == 1


async def test_discover_enter_opens_posting_detail(db_engine: Engine) -> None:
    _seed_scored_posting(db_engine)
    async with AtlasApp(engine=db_engine).run_test() as pilot:
        await pilot.pause()
        await pilot.press("w")
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        assert isinstance(pilot.app.screen, PostingDetailScreen)


async def test_discover_dismiss_removes_row(db_engine: Engine) -> None:
    posting_id = _seed_scored_posting(db_engine)
    async with AtlasApp(engine=db_engine).run_test() as pilot:
        await pilot.pause()
        await pilot.press("w")
        await pilot.pause()
        await pilot.press("x")  # dismiss
        await pilot.pause()
        assert pilot.app.screen.query_one("#discover-table", DataTable).row_count == 0
    with session_scope(db_engine) as session:
        from atlas.scrape.repository import get_posting

        assert get_posting(session, posting_id).queue_status == "dismissed"


async def test_discover_save_keeps_row(db_engine: Engine) -> None:
    posting_id = _seed_scored_posting(db_engine)
    async with AtlasApp(engine=db_engine).run_test() as pilot:
        await pilot.pause()
        await pilot.press("w")
        await pilot.pause()
        await pilot.press("s")  # save
        await pilot.pause()
        assert pilot.app.screen.query_one("#discover-table", DataTable).row_count == 1
    with session_scope(db_engine) as session:
        from atlas.scrape.repository import get_posting

        assert get_posting(session, posting_id).queue_status == "saved"


async def test_discover_open_url(db_engine: Engine) -> None:
    _seed_scored_posting(db_engine, dedupe="d1")
    url_opener = FakeUrlOpener()
    app = AtlasApp(engine=db_engine, url_opener=url_opener)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("w")
        await pilot.pause()
        await pilot.press("o")  # open URL
        await pilot.pause()
    assert url_opener.opened == ["https://jobs.acme.test/d1"]


async def test_discover_open_url_error_is_handled(db_engine: Engine) -> None:
    from atlas.platform.browser import UrlOpenError

    _seed_scored_posting(db_engine)
    url_opener = FakeUrlOpener(raises=UrlOpenError("no browser"))
    app = AtlasApp(engine=db_engine, url_opener=url_opener)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("w")
        await pilot.pause()
        await pilot.press("o")
        await pilot.pause()
        # The error is toasted; the app stays on Discover.
        assert isinstance(pilot.app.screen, DiscoverScreen)


async def test_discover_tailor_navigates_to_application(db_engine: Engine, tmp_path: Path) -> None:
    _seed_scored_posting(db_engine)
    with session_scope(db_engine) as session:
        create_version(
            session,
            raw_markdown="# Sam",
            source_path=None,
            parsed=ParsedResume(
                blocks=[
                    ParsedBlock(
                        type=BlockType.EXPERIENCE, content_id="blk_a", position=0, text="Led it"
                    )
                ]
            ),
            created_at=_NOW,
        )
    provider = FakeLLMProvider([make_response(structured=_TAILORED)])
    app = _action_app(db_engine, provider=provider, renders_dir=tmp_path)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("w")
        await pilot.pause()
        await pilot.press("t")  # tailor
        await app.workers.wait_for_complete()
        await pilot.pause()
        assert isinstance(pilot.app.screen, ApplicationDetailScreen)


async def test_discover_tailor_empty_queue_is_noop(db_engine: Engine, tmp_path: Path) -> None:
    # Action-capable app but an empty queue: tailor finds no row and no-ops.
    provider = FakeLLMProvider([])
    app = _action_app(db_engine, provider=provider, renders_dir=tmp_path)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("w")
        await pilot.pause()
        await pilot.press("t")  # no rows → guard returns, no worker
        await pilot.pause()
        assert isinstance(pilot.app.screen, DiscoverScreen)


async def test_discover_tailor_browse_only_disabled(db_engine: Engine) -> None:
    _seed_scored_posting(db_engine)
    async with AtlasApp(engine=db_engine).run_test() as pilot:
        await pilot.pause()
        await pilot.press("w")
        await pilot.pause()
        await pilot.press("t")  # no provider → disabled, no worker
        await pilot.pause()
        assert isinstance(pilot.app.screen, DiscoverScreen)


async def test_discover_tailor_worker_error_is_handled(db_engine: Engine, tmp_path: Path) -> None:
    # A scored posting (so the queue is populated) but no master resume → tailoring
    # raises in the worker; the app stays on the Discover screen and toasts.
    _seed_scored_posting(db_engine)
    provider = FakeLLMProvider([make_response(structured=_TAILORED)])
    app = _action_app(db_engine, provider=provider, renders_dir=tmp_path)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("w")
        await pilot.pause()
        await pilot.press("t")
        await app.workers.wait_for_complete()
        await pilot.pause()
        assert isinstance(pilot.app.screen, DiscoverScreen)


async def test_posting_detail_tailor_navigates(db_engine: Engine, tmp_path: Path) -> None:
    _seed_scored_posting(db_engine)
    with session_scope(db_engine) as session:
        create_version(
            session,
            raw_markdown="# Sam",
            source_path=None,
            parsed=ParsedResume(
                blocks=[
                    ParsedBlock(
                        type=BlockType.EXPERIENCE, content_id="blk_a", position=0, text="Led it"
                    )
                ]
            ),
            created_at=_NOW,
        )
    provider = FakeLLMProvider([make_response(structured=_TAILORED)])
    app = _action_app(db_engine, provider=provider, renders_dir=tmp_path)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("w")
        await pilot.pause()
        await pilot.press("enter")  # → posting detail
        await pilot.pause()
        assert isinstance(pilot.app.screen, PostingDetailScreen)
        await pilot.press("t")  # tailor from posting detail
        await app.workers.wait_for_complete()
        await pilot.pause()
        assert isinstance(pilot.app.screen, ApplicationDetailScreen)


async def test_posting_detail_tailor_browse_only_disabled(db_engine: Engine) -> None:
    _seed_scored_posting(db_engine)
    async with AtlasApp(engine=db_engine).run_test() as pilot:
        await pilot.pause()
        await pilot.press("w")
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        assert isinstance(pilot.app.screen, PostingDetailScreen)
        await pilot.press("t")  # no provider → disabled
        await pilot.pause()
        assert isinstance(pilot.app.screen, PostingDetailScreen)


async def test_posting_detail_tailor_worker_error_is_handled(
    db_engine: Engine, tmp_path: Path
) -> None:
    # Seed a scored posting (so the active profile's queue is populated) but no
    # master resume, so tailoring raises inside the worker; the app stays on the
    # Posting-detail screen and toasts rather than tearing down.
    _seed_scored_posting(db_engine)
    provider = FakeLLMProvider([make_response(structured=_TAILORED)])
    app = _action_app(db_engine, provider=provider, renders_dir=tmp_path)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("w")
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        await pilot.press("t")
        await app.workers.wait_for_complete()
        await pilot.pause()
        assert isinstance(pilot.app.screen, PostingDetailScreen)
