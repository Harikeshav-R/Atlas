"""Tests for the daemon's scoring poll in :mod:`atlas.daemon.poll`.

Pure over the in-memory ``db_engine`` fixture with a scripted ``FakeLLMProvider``
— no scheduler or process involved (AGENTS.md §6.2).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from atlas.daemon.poll import run_scoring_poll
from atlas.db import session_scope
from atlas.matching.repository import get_latest_match_score
from atlas.profiles.preferences import ProfilePreferences
from atlas.profiles.repository import create_profile
from atlas.resume.repository import create_version
from atlas.resume.structure import BlockType, ParsedBlock, ParsedResume
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
_SCORED = datetime(2026, 8, 4, 9, 30, tzinfo=UTC)


def _fixed_clock() -> _dt:
    return _SCORED


def _assessment() -> dict[str, object]:
    return {
        "score": 78,
        "verdict": "good",
        "rationale": "Good overlap.",
        "matched_strengths": ["Python"],
        "gaps": ["Kubernetes"],
        "dealbreaker_hits": [],
        "salary_fit": "within",
    }


def _seed_posting(engine: Engine, *, title: str, dedupe_hash: str) -> int:
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
            apply_url=f"https://jobs.acme.test/{dedupe_hash}",
            dedupe_hash=dedupe_hash,
            fetched_at=_FETCHED,
            description="Build things.",
            keywords=["python"],
        )
        assert posting.id is not None
        return posting.id


def _seed_profile(engine: Engine) -> None:
    with session_scope(engine) as session:
        create_profile(
            session,
            name="BE",
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
            session, raw_markdown="# Sam", source_path=None, parsed=parsed, created_at=_FETCHED
        )


def test_poll_scores_the_backlog(db_engine: Engine) -> None:
    _seed_profile(db_engine)
    _seed_resume(db_engine)
    p1 = _seed_posting(db_engine, title="A", dedupe_hash="h1")
    p2 = _seed_posting(db_engine, title="B", dedupe_hash="h2")
    provider = FakeLLMProvider(
        [make_response(structured=_assessment()), make_response(structured=_assessment())]
    )
    with session_scope(db_engine) as session:
        outcome = run_scoring_poll(session, provider=provider, clock=_fixed_clock)
    assert outcome.scored == 2
    assert outcome.skipped == 0
    with session_scope(db_engine) as session:
        assert get_latest_match_score(session, p1) is not None
        assert get_latest_match_score(session, p2) is not None


def test_poll_skips_already_scored(db_engine: Engine) -> None:
    _seed_profile(db_engine)
    _seed_resume(db_engine)
    _seed_posting(db_engine, title="A", dedupe_hash="h1")
    # First poll scores the one posting.
    provider = FakeLLMProvider([make_response(structured=_assessment())])
    with session_scope(db_engine) as session:
        run_scoring_poll(session, provider=provider, clock=_fixed_clock)
    # A second poll has nothing to do — the posting is no longer in the backlog.
    empty_provider = FakeLLMProvider([])
    with session_scope(db_engine) as session:
        outcome = run_scoring_poll(session, provider=empty_provider, clock=_fixed_clock)
    assert outcome.scored == 0
    assert outcome.skipped == 0


def test_poll_best_effort_skips_unscoreable(db_engine: Engine) -> None:
    # An active profile but no master resume → score_posting raises
    # NoMasterResumeError (a MatchingError); the poll counts it as skipped rather
    # than aborting the batch.
    _seed_profile(db_engine)
    _seed_posting(db_engine, title="A", dedupe_hash="h1")
    provider = FakeLLMProvider([make_response(structured=_assessment())])
    with session_scope(db_engine) as session:
        outcome = run_scoring_poll(session, provider=provider, clock=_fixed_clock)
    assert outcome.scored == 0
    assert outcome.skipped == 1


def test_poll_no_active_profile_is_a_benign_empty_poll(db_engine: Engine) -> None:
    # With no active profile there is nothing to score against; the unattended
    # daemon poll returns an empty outcome rather than raising.
    _seed_resume(db_engine)
    _seed_posting(db_engine, title="A", dedupe_hash="h1")
    provider = FakeLLMProvider([])
    with session_scope(db_engine) as session:
        outcome = run_scoring_poll(session, provider=provider, clock=_fixed_clock)
    assert outcome.scored == 0
    assert outcome.skipped == 0


def test_poll_empty_backlog(db_engine: Engine) -> None:
    provider = FakeLLMProvider([])
    with session_scope(db_engine) as session:
        outcome = run_scoring_poll(session, provider=provider, clock=_fixed_clock)
    assert outcome.scored == 0
    assert outcome.skipped == 0
