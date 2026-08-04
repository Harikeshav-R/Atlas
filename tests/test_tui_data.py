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
from atlas.profiles.preferences import ProfilePreferences
from atlas.profiles.repository import create_profile
from atlas.scrape.repository import (
    create_job_posting,
    get_or_create_company,
    get_or_create_url_source,
)
from atlas.tailor.errors import ApplicationNotFoundError
from atlas.tailor.repository import create_tailored_resume, get_or_create_application
from atlas.tracking.service import mark_applied, set_application_status
from atlas.tracking.status import ApplicationStatus
from atlas.tui.data import (
    ApplicationDetail,
    DashboardReport,
    build_application_detail,
    build_dashboard_report,
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


# --- serialization ---------------------------------------------------------------


def test_reports_json_round_trip(db_engine: Engine) -> None:
    app_id, _ = _seed_application(db_engine, scored=True, with_materials=True)
    with session_scope(db_engine) as session:
        dashboard = build_dashboard_report(session)
        detail = build_application_detail(session, app_id)
    assert DashboardReport.model_validate_json(dashboard.model_dump_json()) == dashboard
    assert ApplicationDetail.model_validate_json(detail.model_dump_json()) == detail
