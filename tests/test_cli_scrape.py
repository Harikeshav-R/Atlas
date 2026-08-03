"""Tests for the posting reporting/rendering logic in :mod:`atlas.cli.scrape`."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytest
from rich.console import RenderableType

from atlas.cli.console import console
from atlas.cli.scrape import (
    PostingDetail,
    PostingsReport,
    PostingSummary,
    build_posting_detail,
    build_postings_report,
    render_posting_detail,
    render_postings,
)
from atlas.db import session_scope
from atlas.matching.repository import create_match_score
from atlas.profiles.preferences import ProfilePreferences
from atlas.profiles.repository import create_profile
from atlas.scrape.errors import JobPostingNotFoundError
from atlas.scrape.repository import (
    create_job_posting,
    get_or_create_company,
    get_or_create_url_source,
)

if TYPE_CHECKING:
    from sqlalchemy.engine import Engine

_FETCHED = datetime(2026, 8, 3, tzinfo=UTC)


def _seed(engine: Engine, *, title: str = "Backend Engineer", company: str = "Acme") -> int:
    with session_scope(engine) as session:
        comp = get_or_create_company(session, name=company)
        source = get_or_create_url_source(session)
        assert comp.id is not None
        assert source.id is not None
        posting = create_job_posting(
            session,
            source_id=source.id,
            company_id=comp.id,
            title=title,
            apply_url="https://jobs.acme.test/1",
            dedupe_hash=title,
            fetched_at=_FETCHED,
            location="Remote (US)",
            remote_type="remote",
            keywords=["python"],
            description="Build things.",
        )
        assert posting.id is not None
        return posting.id


def _score(engine: Engine, posting_id: int, *, score: int = 82, verdict: str = "strong") -> None:
    """Attach a fit score to a seeded posting so the fit column has data."""
    with session_scope(engine) as session:
        profile = create_profile(
            session, name="Backend Engineer", preferences=ProfilePreferences(), active=True
        )
        assert profile.id is not None
        create_match_score(
            session,
            job_posting_id=posting_id,
            profile_id=profile.id,
            score=score,
            verdict=verdict,
            rationale="Strong overlap.",
            matched_strengths=["Python"],
            gaps=[],
            dealbreaker_hits=[],
            salary_fit="within",
            signals={"salary": "within"},
            model="fake-model",
            created_at=_FETCHED,
        )


def _render(renderable: RenderableType) -> str:
    with console.capture() as capture:
        console.print(renderable)
    return capture.get()


def test_build_postings_report(db_engine: Engine) -> None:
    _seed(db_engine, title="First")
    _seed(db_engine, title="Second")
    with session_scope(db_engine) as session:
        report = build_postings_report(session)
    assert [p.title for p in report.postings] == ["First", "Second"]
    assert report.postings[0].company == "Acme"


def test_build_posting_detail(db_engine: Engine) -> None:
    posting_id = _seed(db_engine)
    with session_scope(db_engine) as session:
        detail = build_posting_detail(session, posting_id)
    assert detail.title == "Backend Engineer"
    assert detail.company == "Acme"
    assert detail.remote_type == "remote"
    assert detail.keywords == ["python"]


def test_build_posting_detail_missing_raises(db_engine: Engine) -> None:
    with session_scope(db_engine) as session, pytest.raises(JobPostingNotFoundError):
        build_posting_detail(session, 999)


def test_build_reports_surface_latest_score(db_engine: Engine) -> None:
    posting_id = _seed(db_engine)
    _score(db_engine, posting_id, score=82, verdict="strong")
    with session_scope(db_engine) as session:
        report = build_postings_report(session)
        detail = build_posting_detail(session, posting_id)
    assert report.postings[0].score == 82
    assert report.postings[0].verdict == "strong"
    assert detail.score == 82
    assert detail.verdict == "strong"


def test_build_reports_leave_score_none_when_unscored(db_engine: Engine) -> None:
    posting_id = _seed(db_engine)
    with session_scope(db_engine) as session:
        report = build_postings_report(session)
        detail = build_posting_detail(session, posting_id)
    assert report.postings[0].score is None
    assert report.postings[0].verdict is None
    assert detail.score is None
    assert detail.verdict is None


def test_render_empty_report_hints_at_add() -> None:
    text = _render(render_postings(PostingsReport(postings=[])))
    assert "atlas add" in text


def test_render_report_shows_postings() -> None:
    report = PostingsReport(
        postings=[
            PostingSummary(
                id=1,
                title="Backend Engineer",
                company="Acme",
                location=None,
                apply_url="https://jobs.acme.test/1",
            )
        ]
    )
    text = _render(render_postings(report))
    assert "Job postings" in text
    assert "Backend Engineer" in text
    # A posting with no location (and no score) renders the em-dash placeholder.
    assert "—" in text


def test_render_report_shows_scored_fit_column() -> None:
    report = PostingsReport(
        postings=[
            PostingSummary(
                id=1,
                title="Backend Engineer",
                company="Acme",
                location="Remote",
                apply_url="https://jobs.acme.test/1",
                score=82,
                verdict="strong",
            )
        ]
    )
    text = _render(render_postings(report))
    assert "82" in text
    assert "strong" in text


def test_render_posting_detail() -> None:
    detail = PostingDetail(
        id=1,
        title="Backend Engineer",
        company="Acme",
        location="Remote",
        remote_type="remote",
        employment_type=None,
        seniority=None,
        keywords=["python", "postgres"],
        apply_url="https://jobs.acme.test/1",
        description="Build things.",
    )
    text = _render(render_posting_detail(detail))
    assert "Backend Engineer" in text
    assert "Acme" in text
    assert "python, postgres" in text
    # Absent fields (and the not-yet-scored fit) render the em-dash placeholder.
    assert "—" in text


def test_render_posting_detail_shows_scored_fit() -> None:
    detail = PostingDetail(
        id=1,
        title="Backend Engineer",
        company="Acme",
        location="Remote",
        remote_type="remote",
        employment_type=None,
        seniority=None,
        keywords=["python"],
        apply_url="https://jobs.acme.test/1",
        description="Build things.",
        score=91,
        verdict="strong",
    )
    text = _render(render_posting_detail(detail))
    assert "91" in text
    assert "strong" in text


def test_reports_json_round_trip() -> None:
    report = PostingsReport(
        postings=[PostingSummary(id=1, title="X", company="Y", location=None, apply_url="u")]
    )
    assert PostingsReport.model_validate_json(report.model_dump_json()) == report
