"""Tests for the application-tracking rendering/reporting in :mod:`atlas.cli.tracking`.

Covers the pure ``build_applications_report`` / ``render_*`` logic (against the
in-memory ``db_engine`` fixture) and the ``list_applications`` repository query,
without invoking the CLI. The status-transition orchestration is covered in
``test_tracking_service``.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from rich.console import RenderableType

from atlas.cli.console import console
from atlas.cli.tracking import (
    ApplicationListReport,
    build_applications_report,
    render_applications,
    render_status_change,
    status_style,
)
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
from atlas.tracking.repository import list_applications
from atlas.tracking.service import StatusChangeOutcome, set_application_status
from atlas.tracking.status import ApplicationStatus

if TYPE_CHECKING:
    from sqlalchemy.engine import Engine

_NOW = datetime(2026, 8, 4, 9, 30, tzinfo=UTC)


def _render(renderable: RenderableType) -> str:
    with console.capture() as capture:
        console.print(renderable)
    return capture.get()


def _seed_application(
    engine: Engine,
    *,
    title: str = "Backend Engineer",
    scored: bool = False,
    profile_name: str = "BE",
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
        profile = create_profile(
            session, name=profile_name, preferences=ProfilePreferences(), active=True
        )
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
        return application.id, profile.id


def test_status_style_maps_and_defaults() -> None:
    assert status_style("offer") == "success"
    assert status_style("rejected") == "bad"
    assert status_style("nonsense") == "muted"


def test_build_report_includes_fit_when_scored(db_engine: Engine) -> None:
    _seed_application(db_engine, scored=True)
    with session_scope(db_engine) as session:
        report = build_applications_report(session)
    assert len(report.applications) == 1
    summary = report.applications[0]
    assert summary.status == "preparing"
    assert summary.title == "Backend Engineer"
    assert summary.company == "Acme"
    assert summary.score == 82
    assert summary.verdict == "strong"


def test_build_report_unscored_has_no_fit(db_engine: Engine) -> None:
    _seed_application(db_engine, scored=False)
    with session_scope(db_engine) as session:
        report = build_applications_report(session)
    summary = report.applications[0]
    assert summary.score is None
    assert summary.verdict is None


def test_build_report_filters_by_status(db_engine: Engine) -> None:
    app_id, _ = _seed_application(db_engine)
    with session_scope(db_engine) as session:
        set_application_status(session, app_id, ApplicationStatus.READY, clock=lambda: _NOW)
    with session_scope(db_engine) as session:
        ready = build_applications_report(session, status=ApplicationStatus.READY)
        preparing = build_applications_report(session, status=ApplicationStatus.PREPARING)
    assert [a.id for a in ready.applications] == [app_id]
    assert preparing.applications == []


def test_list_applications_filters_by_profile(db_engine: Engine) -> None:
    app_id, profile_id = _seed_application(db_engine)
    with session_scope(db_engine) as session:
        for_profile_ids = [a.id for a in list_applications(session, profile_id=profile_id)]
        other = list(list_applications(session, profile_id=profile_id + 999))
    assert for_profile_ids == [app_id]
    assert other == []


def test_render_applications_table_and_empty(db_engine: Engine) -> None:
    empty = _render(render_applications(ApplicationListReport(applications=[])))
    assert "No applications yet" in empty
    _seed_application(db_engine, scored=True)
    with session_scope(db_engine) as session:
        report = build_applications_report(session)
    rendered = _render(render_applications(report))
    assert "Applications" in rendered
    assert "Backend Engineer" in rendered
    assert "preparing" in rendered


def test_render_status_change_full_and_minimal() -> None:
    minimal = StatusChangeOutcome(
        application_id=1,
        previous_status="preparing",
        new_status="ready",
        applied_at=None,
        outcome=None,
        forced=False,
        due=None,
    )
    minimal_text = _render(render_status_change(minimal))
    assert "preparing" in minimal_text
    assert "ready" in minimal_text
    assert "Forced" not in minimal_text

    full = StatusChangeOutcome(
        application_id=2,
        previous_status="ready",
        new_status="applied",
        applied_at=_NOW,
        outcome="offer",
        forced=True,
        due=_NOW,
    )
    full_text = _render(render_status_change(full))
    assert "Forced" in full_text
    assert "Applied" in full_text
    assert "Outcome" in full_text
    assert "Due" in full_text


def test_report_json_round_trip(db_engine: Engine) -> None:
    _seed_application(db_engine, scored=True)
    with session_scope(db_engine) as session:
        report = build_applications_report(session)
    assert ApplicationListReport.model_validate_json(report.model_dump_json()) == report
