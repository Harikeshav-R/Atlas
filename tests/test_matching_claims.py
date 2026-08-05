"""Tests for the scoring-lease claims in :mod:`atlas.matching.claims`.

Pure over the in-memory ``db_engine`` fixture with an injected clock — the lease
logic (fresh / live / stale / release) is exercised without any daemon or process
(AGENTS.md §6.2).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from sqlmodel import select

from atlas.db import session_scope
from atlas.db.models import ScoreClaim
from atlas.matching.claims import DEFAULT_LEASE_SECONDS, release_claim, try_claim
from atlas.profiles.preferences import ProfilePreferences
from atlas.profiles.repository import create_profile
from atlas.scrape.repository import (
    create_job_posting,
    get_or_create_company,
    get_or_create_url_source,
)

if TYPE_CHECKING:
    from sqlalchemy.engine import Engine

_NOW = datetime(2026, 8, 5, 12, 0, tzinfo=UTC)


def _seed_pair(engine: Engine) -> tuple[int, int]:
    """Seed a posting + profile so the score_claim foreign keys resolve."""
    with session_scope(engine) as session:
        company = get_or_create_company(session, name="Acme")
        source = get_or_create_url_source(session)
        assert company.id is not None and source.id is not None
        posting = create_job_posting(
            session,
            source_id=source.id,
            company_id=company.id,
            title="Backend Engineer",
            apply_url="https://jobs.acme.test/1",
            dedupe_hash="h1",
            fetched_at=_NOW,
        )
        profile = create_profile(session, name="BE", preferences=ProfilePreferences())
        assert posting.id is not None and profile.id is not None
        return posting.id, profile.id


def test_try_claim_fresh_pair_succeeds(db_engine: Engine) -> None:
    posting_id, profile_id = _seed_pair(db_engine)
    with session_scope(db_engine) as session:
        got = try_claim(
            session, job_posting_id=posting_id, profile_id=profile_id, owner="pid-1", now=_NOW
        )
        assert got is True
    with session_scope(db_engine) as session:
        claim = session.exec(select(ScoreClaim)).one()
        assert claim.owner == "pid-1"
        assert claim.claimed_at == _NOW


def test_try_claim_live_claim_is_blocked(db_engine: Engine) -> None:
    posting_id, profile_id = _seed_pair(db_engine)
    with session_scope(db_engine) as session:
        try_claim(
            session, job_posting_id=posting_id, profile_id=profile_id, owner="pid-1", now=_NOW
        )
    # A second worker a moment later finds a live claim and is refused.
    later = _NOW + timedelta(seconds=5)
    with session_scope(db_engine) as session:
        got = try_claim(
            session, job_posting_id=posting_id, profile_id=profile_id, owner="pid-2", now=later
        )
        assert got is False
    with session_scope(db_engine) as session:
        claim = session.exec(select(ScoreClaim)).one()
        assert claim.owner == "pid-1"  # the original owner still holds it


def test_try_claim_steals_a_stale_claim(db_engine: Engine) -> None:
    posting_id, profile_id = _seed_pair(db_engine)
    with session_scope(db_engine) as session:
        try_claim(
            session, job_posting_id=posting_id, profile_id=profile_id, owner="pid-1", now=_NOW
        )
    # Past the lease → the claim is abandoned and can be stolen.
    stale = _NOW + timedelta(seconds=DEFAULT_LEASE_SECONDS)
    with session_scope(db_engine) as session:
        got = try_claim(
            session, job_posting_id=posting_id, profile_id=profile_id, owner="pid-2", now=stale
        )
        assert got is True
    with session_scope(db_engine) as session:
        claim = session.exec(select(ScoreClaim)).one()
        assert claim.owner == "pid-2"
        assert claim.claimed_at == stale


def test_release_claim_frees_the_pair(db_engine: Engine) -> None:
    posting_id, profile_id = _seed_pair(db_engine)
    with session_scope(db_engine) as session:
        try_claim(
            session, job_posting_id=posting_id, profile_id=profile_id, owner="pid-1", now=_NOW
        )
    with session_scope(db_engine) as session:
        release_claim(session, job_posting_id=posting_id, profile_id=profile_id)
    with session_scope(db_engine) as session:
        assert session.exec(select(ScoreClaim)).first() is None
        # After release, a fresh claim succeeds again.
        assert try_claim(
            session, job_posting_id=posting_id, profile_id=profile_id, owner="pid-2", now=_NOW
        )


def test_release_claim_missing_is_a_no_op(db_engine: Engine) -> None:
    posting_id, profile_id = _seed_pair(db_engine)
    with session_scope(db_engine) as session:
        release_claim(session, job_posting_id=posting_id, profile_id=profile_id)  # no error
        assert session.exec(select(ScoreClaim)).first() is None
