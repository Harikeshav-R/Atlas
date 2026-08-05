"""Tests for the pure TUI view-model builders in :mod:`atlas.tui.data`.

These run against the in-memory ``db_engine`` fixture with no Textual in the loop
— the data logic the screens present is fully exercised here (AGENTS.md §6.2).
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytest

from atlas.coverletter.repository import create_cover_letter
from atlas.db import session_scope
from atlas.matching.repository import create_match_score
from atlas.matching.structure import QueueStatus
from atlas.profiles.preferences import ProfilePreferences
from atlas.profiles.repository import create_profile, get_active_profile, set_active_profile
from atlas.resume.repository import create_version
from atlas.resume.structure import BlockType, ParsedBlock, ParsedResume
from atlas.scrape.repository import (
    create_job_posting,
    get_or_create_company,
    get_or_create_url_source,
    set_posting_queue_status,
)
from atlas.tailor.errors import ApplicationNotFoundError
from atlas.tailor.repository import create_tailored_resume, get_or_create_application
from atlas.tracking.service import mark_applied, set_application_status
from atlas.tracking.status import ApplicationStatus
from atlas.tui.data import (
    ApplicationDetail,
    DashboardReport,
    TailorWorkspaceView,
    build_application_detail,
    build_dashboard_report,
    build_discover_queue,
    build_profile_choices,
    build_tailor_workspace,
)

if TYPE_CHECKING:
    from sqlalchemy.engine import Engine

_NOW = datetime(2026, 8, 4, 9, 30, tzinfo=UTC)


def _fixed(moment: datetime) -> Callable[[], datetime]:
    return lambda: moment


def _seed_application(
    engine: Engine,
    *,
    title: str = "Backend Engineer",
    scored: bool = False,
    with_materials: bool = False,
) -> tuple[int, int]:
    """Create a posting + profile + application; return (application_id, profile_id)."""
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
            apply_url=f"https://jobs.acme.test/{title}",
            dedupe_hash=title,
            fetched_at=_NOW,
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
        if with_materials:
            create_tailored_resume(
                session,
                application_id=application.id,
                master_resume_version=1,
                selections=[],
                final_content={},
                rendered_pdf_ref="renders/r.pdf",
                decisions=[],
                created_at=_NOW,
            )
            create_cover_letter(
                session,
                application_id=application.id,
                content={},
                tone="professional",
                rendered_pdf_ref="renders/c.pdf",
                created_at=_NOW,
            )
        return application.id, profile.id


# --- build_dashboard_report ------------------------------------------------------


def test_dashboard_empty(db_engine: Engine) -> None:
    with session_scope(db_engine) as session:
        report = build_dashboard_report(session)
    assert report.active_profile is None
    assert report.total_applications == 0
    # Funnel is padded to the full status set, all zero.
    assert len(report.funnel) == len(ApplicationStatus)
    assert all(bar.count == 0 for bar in report.funnel)
    assert report.recent == []
    assert report.deadlines == []


def test_dashboard_counts_and_recent(db_engine: Engine) -> None:
    _seed_application(db_engine)
    with session_scope(db_engine) as session:
        report = build_dashboard_report(session)
    assert report.active_profile == "BE"
    assert report.total_applications == 1
    preparing = next(bar for bar in report.funnel if bar.status == "preparing")
    assert preparing.count == 1
    assert report.recent[0].title == "Backend Engineer"
    assert report.recent[0].status == "preparing"


def test_dashboard_recent_limit(db_engine: Engine) -> None:
    for i in range(3):
        _seed_application(db_engine, title=f"Role {i}")
    with session_scope(db_engine) as session:
        report = build_dashboard_report(session, recent_limit=2)
    assert report.total_applications == 3
    assert len(report.recent) == 2


def test_dashboard_deadlines_sorted_and_latest_due(db_engine: Engine) -> None:
    app_id, _ = _seed_application(db_engine)
    early = datetime(2026, 8, 10, tzinfo=UTC)
    late = datetime(2026, 8, 20, tzinfo=UTC)
    with session_scope(db_engine) as session:
        set_application_status(session, app_id, ApplicationStatus.READY, clock=_fixed(_NOW))
    with session_scope(db_engine) as session:
        set_application_status(
            session, app_id, ApplicationStatus.APPLIED, due=late, clock=_fixed(_NOW)
        )
    # A later transition with an earlier due date supersedes the recorded deadline.
    with session_scope(db_engine) as session:
        set_application_status(session, app_id, ApplicationStatus.OA, due=early, clock=_fixed(_NOW))
    with session_scope(db_engine) as session:
        report = build_dashboard_report(session)
    assert len(report.deadlines) == 1
    assert report.deadlines[0].due == early


def test_dashboard_no_deadline_when_none_recorded(db_engine: Engine) -> None:
    app_id, _ = _seed_application(db_engine)
    with session_scope(db_engine) as session:
        set_application_status(session, app_id, ApplicationStatus.READY, clock=_fixed(_NOW))
    with session_scope(db_engine) as session:
        report = build_dashboard_report(session)
    assert report.deadlines == []


# --- build_application_detail ----------------------------------------------------


def test_application_detail_minimal(db_engine: Engine) -> None:
    app_id, _ = _seed_application(db_engine)
    with session_scope(db_engine) as session:
        detail = build_application_detail(session, app_id)
    assert detail.id == app_id
    assert detail.title == "Backend Engineer"
    assert detail.status == "preparing"
    assert detail.applied_at is None
    assert detail.outcome is None
    assert detail.score is None
    assert detail.verdict is None
    assert detail.tailored_resume is None
    assert detail.cover_letter is None
    assert detail.timeline == []


def test_application_detail_full(db_engine: Engine) -> None:
    app_id, _ = _seed_application(db_engine, scored=True, with_materials=True)
    with session_scope(db_engine) as session:
        set_application_status(session, app_id, ApplicationStatus.READY, clock=_fixed(_NOW))
    with session_scope(db_engine) as session:
        mark_applied(session, app_id, clock=_fixed(_NOW))
    with session_scope(db_engine) as session:
        detail = build_application_detail(session, app_id)
    assert detail.status == "applied"
    assert detail.applied_at is not None
    assert detail.score == 82
    assert detail.verdict == "strong"
    assert detail.tailored_resume is not None
    assert detail.tailored_resume.version == 1
    assert detail.tailored_resume.path == "renders/r.pdf"
    assert detail.cover_letter is not None
    assert detail.cover_letter.path == "renders/c.pdf"
    assert [e.to_status for e in detail.timeline] == ["ready", "applied"]


def test_application_detail_unknown_raises(db_engine: Engine) -> None:
    with session_scope(db_engine) as session, pytest.raises(ApplicationNotFoundError):
        build_application_detail(session, 999)


# --- build_tailor_workspace ------------------------------------------------------


def _add_master_resume(engine: Engine) -> None:
    with session_scope(engine) as session:
        parsed = ParsedResume(
            blocks=[
                ParsedBlock(
                    type=BlockType.EXPERIENCE,
                    content_id="blk_a",
                    position=0,
                    text="Led the platform team",
                )
            ]
        )
        create_version(
            session, raw_markdown="# Sam", source_path=None, parsed=parsed, created_at=_NOW
        )


def test_tailor_workspace_minimal(db_engine: Engine) -> None:
    app_id, _ = _seed_application(db_engine)
    with session_scope(db_engine) as session:
        view = build_tailor_workspace(session, app_id)
    assert view.application_id == app_id
    assert view.job_posting_id > 0
    assert view.title == "Backend Engineer"
    assert view.master_blocks == []  # no master resume seeded
    assert view.selections == []
    assert view.resume_version is None
    assert view.resume_path is None
    assert view.cover_version is None


def test_tailor_workspace_with_master_and_materials(db_engine: Engine) -> None:
    app_id, _ = _seed_application(db_engine, with_materials=True)
    _add_master_resume(db_engine)
    # Give the tailored resume real selections to decode.
    with session_scope(db_engine) as session:
        create_tailored_resume(
            session,
            application_id=app_id,
            master_resume_version=1,
            selections=[
                {
                    "content_id": "blk_a",
                    "block_type": "experience",
                    "final_text": "Led the platform team",
                    "reason": "core",
                    "included": True,
                }
            ],
            final_content={},
            rendered_pdf_ref="renders/r2.pdf",
            decisions=[],
            created_at=_NOW,
        )
    with session_scope(db_engine) as session:
        view = build_tailor_workspace(session, app_id)
    assert [b.content_id for b in view.master_blocks] == ["blk_a"]
    assert len(view.selections) == 1
    assert view.selections[0].content_id == "blk_a"
    assert view.selections[0].included is True
    assert view.selections[0].final_text == "Led the platform team"
    assert view.resume_version == 2  # the second tailored resume
    assert view.resume_path == "renders/r2.pdf"
    assert view.cover_version == 1


def test_tailor_workspace_unknown_raises(db_engine: Engine) -> None:
    with session_scope(db_engine) as session, pytest.raises(ApplicationNotFoundError):
        build_tailor_workspace(session, 999)


# --- build_discover_queue --------------------------------------------------------


def _active_profile_id(engine: Engine) -> int:
    """Return the active profile's id, creating one once if none exists.

    The discover-queue tests seed several postings under one shared active
    profile (the queue is scored per active profile), so profile creation is
    idempotent here rather than per-posting.
    """
    with session_scope(engine) as session:
        existing = get_active_profile(session)
        if existing is not None:
            assert existing.id is not None
            return existing.id
        profile = create_profile(session, name="BE", preferences=ProfilePreferences(), active=True)
        assert profile.id is not None
        return profile.id


def _seed_scored(engine: Engine, *, dedupe: str, score: int, salary: dict[str, object]) -> int:
    """Create a scored bare posting (under the shared active profile); return its id."""
    profile_id = _active_profile_id(engine)
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
            apply_url=f"https://jobs.acme.test/{dedupe}",
            dedupe_hash=dedupe,
            fetched_at=_NOW,
            location="Remote",
            salary=salary,
        )
        assert posting.id is not None
        create_match_score(
            session,
            job_posting_id=posting.id,
            profile_id=profile_id,
            score=score,
            verdict="strong",
            rationale=f"Fit {dedupe}.",
            matched_strengths=[],
            gaps=[],
            dealbreaker_hits=[],
            salary_fit="within",
            signals={},
            model="fake",
            created_at=_NOW,
        )
        return posting.id


def test_discover_queue_maps_fields_and_ranks(db_engine: Engine) -> None:
    _seed_scored(db_engine, dedupe="d1", score=70, salary={"min": 150000, "currency": "USD"})
    _seed_scored(db_engine, dedupe="d2", score=90, salary={})
    with session_scope(db_engine) as session:
        queue = build_discover_queue(session)
    assert [row.score for row in queue.rows] == [90, 70]  # ranked by fit
    top = queue.rows[0]
    assert top.company == "Acme"
    assert top.source == "url"
    assert top.salary == "—"  # empty salary JSON
    assert top.verdict == "strong"
    assert queue.rows[1].salary == "150000 USD"  # min-only + currency


def test_discover_queue_salary_display_variants(db_engine: Engine) -> None:
    _seed_scored(db_engine, dedupe="rng", score=80, salary={"min": 120000, "max": 150000})
    _seed_scored(db_engine, dedupe="max", score=70, salary={"max": 90000, "currency": "EUR"})
    with session_scope(db_engine) as session:
        rows = {row.id: row for row in build_discover_queue(session).rows}
    salaries = {row.salary for row in rows.values()}
    assert "120000 - 150000" in salaries  # min+max, no currency
    assert "90000 EUR" in salaries  # max-only + currency


def test_discover_queue_excludes_dismissed(db_engine: Engine) -> None:
    p1 = _seed_scored(db_engine, dedupe="d1", score=80, salary={})
    _seed_scored(db_engine, dedupe="d2", score=90, salary={})
    with session_scope(db_engine) as session:
        set_posting_queue_status(session, p1, QueueStatus.DISMISSED)
    with session_scope(db_engine) as session:
        queue = build_discover_queue(session)
    assert [row.id for row in queue.rows] == [row.id for row in queue.rows if row.id != p1]
    assert all(row.id != p1 for row in queue.rows)


def test_discover_queue_empty(db_engine: Engine) -> None:
    with session_scope(db_engine) as session:
        assert build_discover_queue(session).rows == []


def test_discover_queue_is_per_active_profile(db_engine: Engine) -> None:
    # Two profiles, each with its own scored posting; the queue shows the active
    # profile's, and switching the active profile re-ranks to the other's.
    p_backend = _active_profile_id(db_engine)
    posting_be = _seed_scored(db_engine, dedupe="be", score=80, salary={})
    with session_scope(db_engine) as session:
        ml = create_profile(session, name="ML", preferences=ProfilePreferences(), active=True)
        assert ml.id is not None
        ml_id = ml.id
    posting_ml = _seed_scored(db_engine, dedupe="ml", score=90, salary={})
    with session_scope(db_engine) as session:
        # ML is active now → only its posting shows.
        assert [row.id for row in build_discover_queue(session).rows] == [posting_ml]
    with session_scope(db_engine) as session:
        set_active_profile(session, p_backend)
    with session_scope(db_engine) as session:
        assert [row.id for row in build_discover_queue(session).rows] == [posting_be]
    assert ml_id != p_backend


# --- build_profile_choices -------------------------------------------------------


def test_build_profile_choices_marks_active(db_engine: Engine) -> None:
    with session_scope(db_engine) as session:
        create_profile(session, name="Backend", preferences=ProfilePreferences(), active=True)
        create_profile(session, name="ML", preferences=ProfilePreferences(), active=True)
    with session_scope(db_engine) as session:
        choices = build_profile_choices(session)
    names = [(c.name, c.active) for c in choices.choices]
    # Creation order; the last-created active profile is the sole active one.
    assert names == [("Backend", False), ("ML", True)]


def test_build_profile_choices_empty(db_engine: Engine) -> None:
    with session_scope(db_engine) as session:
        assert build_profile_choices(session).choices == []


# --- serialization ---------------------------------------------------------------


def test_reports_json_round_trip(db_engine: Engine) -> None:
    app_id, _ = _seed_application(db_engine, scored=True, with_materials=True)
    _add_master_resume(db_engine)
    with session_scope(db_engine) as session:
        dashboard = build_dashboard_report(session)
        detail = build_application_detail(session, app_id)
        workspace = build_tailor_workspace(session, app_id)
    assert DashboardReport.model_validate_json(dashboard.model_dump_json()) == dashboard
    assert ApplicationDetail.model_validate_json(detail.model_dump_json()) == detail
    assert TailorWorkspaceView.model_validate_json(workspace.model_dump_json()) == workspace
