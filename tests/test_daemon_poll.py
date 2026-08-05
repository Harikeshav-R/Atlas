"""Tests for the daemon's scoring poll in :mod:`atlas.daemon.poll`.

Pure over the in-memory ``db_engine`` fixture with a scripted ``FakeLLMProvider``
— no scheduler or process involved (AGENTS.md §6.2).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlmodel import select

from atlas.daemon.poll import run_scoring_poll
from atlas.db import session_scope
from atlas.db.models import MatchScore
from atlas.matching.claims import try_claim
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


def _seed_profile(engine: Engine, *, name: str = "BE", active: bool = True) -> int:
    with session_scope(engine) as session:
        profile = create_profile(
            session,
            name=name,
            preferences=ProfilePreferences(target_roles=[name]),
            active=active,
        )
        assert profile.id is not None
        return profile.id


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
        outcome = run_scoring_poll(session, provider=provider, owner="pid-1", clock=_fixed_clock)
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
        run_scoring_poll(session, provider=provider, owner="pid-1", clock=_fixed_clock)
    # A second poll has nothing to do — the posting is no longer in the backlog.
    empty_provider = FakeLLMProvider([])
    with session_scope(db_engine) as session:
        outcome = run_scoring_poll(
            session, provider=empty_provider, owner="pid-1", clock=_fixed_clock
        )
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
        outcome = run_scoring_poll(session, provider=provider, owner="pid-1", clock=_fixed_clock)
    assert outcome.scored == 0
    assert outcome.skipped == 1


def test_poll_no_profiles_is_a_benign_empty_poll(db_engine: Engine) -> None:
    # With no profiles at all there is nothing to score against; the unattended
    # daemon poll returns an empty outcome rather than raising.
    _seed_resume(db_engine)
    _seed_posting(db_engine, title="A", dedupe_hash="h1")
    provider = FakeLLMProvider([])
    with session_scope(db_engine) as session:
        outcome = run_scoring_poll(session, provider=provider, owner="pid-1", clock=_fixed_clock)
    assert outcome.scored == 0
    assert outcome.skipped == 0


def test_poll_empty_backlog(db_engine: Engine) -> None:
    provider = FakeLLMProvider([])
    with session_scope(db_engine) as session:
        outcome = run_scoring_poll(session, provider=provider, owner="pid-1", clock=_fixed_clock)
    assert outcome.scored == 0
    assert outcome.skipped == 0


def test_poll_scores_every_profile(db_engine: Engine) -> None:
    # Two profiles x two postings -> four scores, each posting scored once per
    # profile; a second poll finds nothing new.
    _seed_profile(db_engine, name="Backend Engineer")
    _seed_profile(db_engine, name="ML Engineer", active=False)
    _seed_resume(db_engine)
    p1 = _seed_posting(db_engine, title="A", dedupe_hash="h1")
    p2 = _seed_posting(db_engine, title="B", dedupe_hash="h2")
    provider = FakeLLMProvider([make_response(structured=_assessment()) for _ in range(4)])
    with session_scope(db_engine) as session:
        outcome = run_scoring_poll(session, provider=provider, owner="pid-1", clock=_fixed_clock)
    assert outcome.scored == 4
    assert outcome.skipped == 0
    with session_scope(db_engine) as session:
        # Each (posting, profile) pair has its own score row.
        rows = session.exec(select(MatchScore)).all()
        pairs = {(r.job_posting_id, r.profile_id) for r in rows}
        assert len(pairs) == 4
        assert {p1, p2} == {jp for jp, _ in pairs}
    # Re-poll: every pair is already scored, so nothing new.
    with session_scope(db_engine) as session:
        again = run_scoring_poll(
            session, provider=FakeLLMProvider([]), owner="pid-1", clock=_fixed_clock
        )
    assert again.scored == 0


def test_poll_skips_pairs_claimed_by_another_worker(db_engine: Engine) -> None:
    # A live claim held by a different owner blocks the poll from scoring that pair.
    profile_id = _seed_profile(db_engine)
    _seed_resume(db_engine)
    p1 = _seed_posting(db_engine, title="A", dedupe_hash="h1")
    with session_scope(db_engine) as session:
        try_claim(
            session,
            job_posting_id=p1,
            profile_id=profile_id,
            owner="other-pid",
            now=_SCORED,
        )
    provider = FakeLLMProvider([])  # must not be called
    with session_scope(db_engine) as session:
        outcome = run_scoring_poll(session, provider=provider, owner="pid-1", clock=_fixed_clock)
    assert outcome.scored == 0
    assert outcome.claimed == 1
    with session_scope(db_engine) as session:
        assert get_latest_match_score(session, p1) is None
