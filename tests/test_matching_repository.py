"""Tests for fit-score persistence in :mod:`atlas.matching.repository`."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from atlas.db import session_scope
from atlas.matching.repository import create_match_score, get_latest_match_score
from atlas.profiles.preferences import ProfilePreferences
from atlas.profiles.repository import create_profile
from atlas.scrape.repository import (
    create_job_posting,
    get_or_create_company,
    get_or_create_url_source,
)

if TYPE_CHECKING:
    from sqlalchemy.engine import Engine

_CREATED = datetime(2026, 8, 3, 10, 0, tzinfo=UTC)


def _seed_refs(engine: Engine) -> tuple[int, int]:
    """Seed a posting + profile so the match_score foreign keys resolve."""
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
            dedupe_hash="hash",
            fetched_at=_CREATED,
        )
        profile = create_profile(
            session, name="Backend Engineer", preferences=ProfilePreferences(), active=True
        )
        assert posting.id is not None
        assert profile.id is not None
        return posting.id, profile.id


def _create(
    engine: Engine,
    *,
    job_posting_id: int,
    profile_id: int,
    score: int,
    created_at: datetime = _CREATED,
) -> int:
    with session_scope(engine) as session:
        row = create_match_score(
            session,
            job_posting_id=job_posting_id,
            profile_id=profile_id,
            score=score,
            verdict="good",
            rationale="Solid overlap.",
            matched_strengths=["Python"],
            gaps=["Kubernetes"],
            dealbreaker_hits=[],
            salary_fit="within",
            signals={"salary": "within"},
            model="fake-model",
            created_at=created_at,
        )
        assert row.id is not None
        return row.id


def test_create_match_score_persists_fields(db_engine: Engine) -> None:
    posting_id, profile_id = _seed_refs(db_engine)
    _create(db_engine, job_posting_id=posting_id, profile_id=profile_id, score=72)
    with session_scope(db_engine) as session:
        latest = get_latest_match_score(session, posting_id)
        assert latest is not None
        assert latest.score == 72
        assert latest.matched_strengths == ["Python"]
        assert latest.gaps == ["Kubernetes"]
        assert latest.signals == {"salary": "within"}
        assert latest.created_at == _CREATED
        assert latest.created_at.tzinfo is UTC


def test_get_latest_match_score_none_when_unscored(db_engine: Engine) -> None:
    with session_scope(db_engine) as session:
        assert get_latest_match_score(session, 999) is None


def test_get_latest_match_score_returns_newest(db_engine: Engine) -> None:
    # Append-only: two scores for the same posting; the latest-inserted wins.
    posting_id, profile_id = _seed_refs(db_engine)
    _create(db_engine, job_posting_id=posting_id, profile_id=profile_id, score=60)
    _create(db_engine, job_posting_id=posting_id, profile_id=profile_id, score=90)
    with session_scope(db_engine) as session:
        latest = get_latest_match_score(session, posting_id)
        assert latest is not None
        assert latest.score == 90
