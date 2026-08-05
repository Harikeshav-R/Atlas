"""Tests for fit-score persistence in :mod:`atlas.matching.repository`."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytest

from atlas.db import session_scope
from atlas.matching.repository import (
    create_match_score,
    get_latest_match_score,
    list_scored_postings,
)
from atlas.matching.structure import QueueStatus
from atlas.profiles.preferences import ProfilePreferences
from atlas.profiles.repository import create_profile
from atlas.scrape.repository import (
    create_job_posting,
    get_or_create_company,
    get_or_create_url_source,
    set_posting_queue_status,
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


def _add_posting(engine: Engine, *, dedupe: str, title: str = "Role") -> int:
    """Create another posting sharing the seeded company/source; return its id."""
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
            fetched_at=_CREATED,
        )
        assert posting.id is not None
        return posting.id


def test_list_scored_postings_orders_by_score_desc(db_engine: Engine) -> None:
    p1, profile_id = _seed_refs(db_engine)
    p2 = _add_posting(db_engine, dedupe="h2")
    p3 = _add_posting(db_engine, dedupe="h3")
    _create(db_engine, job_posting_id=p1, profile_id=profile_id, score=60)
    _create(db_engine, job_posting_id=p2, profile_id=profile_id, score=90)
    _create(db_engine, job_posting_id=p3, profile_id=profile_id, score=75)
    with session_scope(db_engine) as session:
        rows = list_scored_postings(session)
        assert [posting.id for posting, _ in rows] == [p2, p3, p1]
        assert [score.score for _, score in rows] == [90, 75, 60]


def test_list_scored_postings_uses_latest_score_not_highest(db_engine: Engine) -> None:
    # A posting whose newest score is LOWER than an earlier one ranks by the latest.
    p1, profile_id = _seed_refs(db_engine)
    p2 = _add_posting(db_engine, dedupe="h2")
    _create(db_engine, job_posting_id=p1, profile_id=profile_id, score=95)  # older, high
    _create(db_engine, job_posting_id=p1, profile_id=profile_id, score=40)  # newer, low
    _create(db_engine, job_posting_id=p2, profile_id=profile_id, score=70)
    with session_scope(db_engine) as session:
        rows = list_scored_postings(session)
        # p1's latest score is 40 (< p2's 70), so p2 ranks first.
        assert [posting.id for posting, _ in rows] == [p2, p1]
        assert [score.score for _, score in rows] == [70, 40]


def test_list_scored_postings_tiebreak_newest_posting_first(db_engine: Engine) -> None:
    p1, profile_id = _seed_refs(db_engine)
    p2 = _add_posting(db_engine, dedupe="h2")
    _create(db_engine, job_posting_id=p1, profile_id=profile_id, score=80)
    _create(db_engine, job_posting_id=p2, profile_id=profile_id, score=80)
    with session_scope(db_engine) as session:
        rows = list_scored_postings(session)
        # Equal scores → newer posting (higher id) first.
        assert [posting.id for posting, _ in rows] == [p2, p1]


def test_list_scored_postings_excludes_dismissed(db_engine: Engine) -> None:
    p1, profile_id = _seed_refs(db_engine)
    p2 = _add_posting(db_engine, dedupe="h2")
    _create(db_engine, job_posting_id=p1, profile_id=profile_id, score=80)
    _create(db_engine, job_posting_id=p2, profile_id=profile_id, score=90)
    with session_scope(db_engine) as session:
        set_posting_queue_status(session, p2, QueueStatus.DISMISSED)
    with session_scope(db_engine) as session:
        rows = list_scored_postings(session)
        assert [posting.id for posting, _ in rows] == [p1]


def test_list_scored_postings_includes_saved(db_engine: Engine) -> None:
    p1, profile_id = _seed_refs(db_engine)
    _create(db_engine, job_posting_id=p1, profile_id=profile_id, score=80)
    with session_scope(db_engine) as session:
        set_posting_queue_status(session, p1, QueueStatus.SAVED)
    with session_scope(db_engine) as session:
        rows = list_scored_postings(session)
        assert [posting.id for posting, _ in rows] == [p1]
        assert rows[0][0].queue_status == "saved"


def test_list_scored_postings_excludes_unscored(db_engine: Engine) -> None:
    p1, profile_id = _seed_refs(db_engine)
    _add_posting(db_engine, dedupe="h2")  # never scored → excluded
    _create(db_engine, job_posting_id=p1, profile_id=profile_id, score=80)
    with session_scope(db_engine) as session:
        rows = list_scored_postings(session)
        assert [posting.id for posting, _ in rows] == [p1]


def test_list_scored_postings_empty(db_engine: Engine) -> None:
    with session_scope(db_engine) as session:
        assert list(list_scored_postings(session)) == []


def test_set_posting_queue_status_persists(db_engine: Engine) -> None:
    p1, _ = _seed_refs(db_engine)
    with session_scope(db_engine) as session:
        updated = set_posting_queue_status(session, p1, QueueStatus.DISMISSED)
        assert updated.queue_status == "dismissed"
    with session_scope(db_engine) as session:
        rows = list_scored_postings(session)  # dismissed → gone from the queue
        assert rows == []


def test_set_posting_queue_status_unknown_id_raises(db_engine: Engine) -> None:
    from atlas.scrape.errors import JobPostingNotFoundError

    with session_scope(db_engine) as session, pytest.raises(JobPostingNotFoundError):
        set_posting_queue_status(session, 999, QueueStatus.SAVED)
