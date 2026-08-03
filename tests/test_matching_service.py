"""Tests for the scoring orchestration in :mod:`atlas.matching.service`."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytest

from atlas.db import session_scope
from atlas.matching.errors import NoActiveProfileError, NoMasterResumeError, ScoringError
from atlas.matching.repository import get_latest_match_score
from atlas.matching.service import score_posting
from atlas.profiles.preferences import ProfilePreferences
from atlas.profiles.repository import create_profile
from atlas.resume.repository import create_version
from atlas.resume.structure import BlockType, ParsedBlock, ParsedResume
from atlas.scrape.errors import JobPostingNotFoundError
from atlas.scrape.repository import (
    create_job_posting,
    get_or_create_company,
    get_or_create_url_source,
)
from tests.conftest import FakeLLMProvider, make_response

if TYPE_CHECKING:
    from datetime import datetime as _dt

    from sqlalchemy.engine import Engine

_FETCHED = datetime(2026, 8, 3, 9, 0, tzinfo=UTC)
_SCORED = datetime(2026, 8, 3, 12, 0, tzinfo=UTC)


def _fixed_clock() -> _dt:
    return _SCORED


def _assessment() -> dict[str, object]:
    return {
        "score": 78,
        "verdict": "good",
        "rationale": "Good overlap on the core stack.",
        "matched_strengths": ["Python"],
        "gaps": ["Kubernetes"],
        "dealbreaker_hits": [],
        "salary_fit": "within",
    }


def _seed_posting(engine: Engine, *, description: str = "Build things.") -> int:
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
            fetched_at=_FETCHED,
            description=description,
            requirements={"must": ["Python"]},
            keywords=["python"],
        )
        assert posting.id is not None
        return posting.id


def _seed_profile(engine: Engine) -> None:
    with session_scope(engine) as session:
        create_profile(
            session,
            name="Backend Engineer",
            preferences=ProfilePreferences(target_roles=["Backend Engineer"]),
            active=True,
        )


def _seed_resume(engine: Engine) -> None:
    with session_scope(engine) as session:
        parsed = ParsedResume(
            blocks=[
                ParsedBlock(
                    type=BlockType.SUMMARY,
                    content_id="blk_1",
                    position=0,
                    text="Senior backend engineer",
                )
            ]
        )
        create_version(
            session,
            raw_markdown="# Sam",
            source_path="/home/sam/resume.md",
            parsed=parsed,
            created_at=_FETCHED,
        )


def test_score_posting_persists_and_returns_outcome(db_engine: Engine) -> None:
    posting_id = _seed_posting(db_engine)
    _seed_profile(db_engine)
    _seed_resume(db_engine)
    provider = FakeLLMProvider([make_response(structured=_assessment())], name="fake-backend")
    with session_scope(db_engine) as session:
        outcome = score_posting(session, posting_id, provider=provider, clock=_fixed_clock)
    assert outcome.posting_id == posting_id
    assert outcome.title == "Backend Engineer"
    assert outcome.company == "Acme"
    assert outcome.score == 78
    assert outcome.verdict == "good"
    assert outcome.salary_fit == "within"
    # The persisted row carries the model (provider name) and the injected clock.
    with session_scope(db_engine) as session:
        latest = get_latest_match_score(session, posting_id)
        assert latest is not None
        assert latest.model == "fake-backend"
        assert latest.created_at == _SCORED
        assert latest.signals["salary"] in {"above", "within", "below", "unknown"}


def test_score_posting_appends_history(db_engine: Engine) -> None:
    posting_id = _seed_posting(db_engine)
    _seed_profile(db_engine)
    _seed_resume(db_engine)
    first = dict(_assessment(), score=60)
    second = dict(_assessment(), score=90)
    provider = FakeLLMProvider([make_response(structured=first), make_response(structured=second)])
    with session_scope(db_engine) as session:
        score_posting(session, posting_id, provider=provider, clock=_fixed_clock)
    with session_scope(db_engine) as session:
        score_posting(session, posting_id, provider=provider, clock=_fixed_clock)
    # Two append-only rows; the queue surfaces the latest (90).
    with session_scope(db_engine) as session:
        latest = get_latest_match_score(session, posting_id)
        assert latest is not None
        assert latest.score == 90


def test_score_posting_unknown_id_raises(db_engine: Engine) -> None:
    _seed_profile(db_engine)
    _seed_resume(db_engine)
    provider = FakeLLMProvider([])
    with session_scope(db_engine) as session, pytest.raises(JobPostingNotFoundError):
        score_posting(session, 999, provider=provider)


def test_score_posting_no_active_profile_raises(db_engine: Engine) -> None:
    posting_id = _seed_posting(db_engine)
    _seed_resume(db_engine)
    provider = FakeLLMProvider([])
    with session_scope(db_engine) as session, pytest.raises(NoActiveProfileError):
        score_posting(session, posting_id, provider=provider)


def test_score_posting_no_master_resume_raises(db_engine: Engine) -> None:
    posting_id = _seed_posting(db_engine)
    _seed_profile(db_engine)
    provider = FakeLLMProvider([])
    with session_scope(db_engine) as session, pytest.raises(NoMasterResumeError):
        score_posting(session, posting_id, provider=provider)


def test_score_posting_wraps_output_error_as_scoring_error(db_engine: Engine) -> None:
    posting_id = _seed_posting(db_engine)
    _seed_profile(db_engine)
    _seed_resume(db_engine)
    # The AI never returns schema-valid JSON → LLMOutputError → ScoringError.
    provider = FakeLLMProvider([make_response(text="no json") for _ in range(4)])
    with session_scope(db_engine) as session, pytest.raises(ScoringError):
        score_posting(session, posting_id, provider=provider)
