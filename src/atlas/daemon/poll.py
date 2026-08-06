"""The daemon's scheduled scoring poll (PROJECT.md §4.1, §5.6).

This is the daemon's real work, written as a **pure function over an open**
:class:`~sqlmodel.Session` (like the service layer elsewhere) so it is tested
directly with the in-memory ``db_engine`` fixture and a fake provider, with no
scheduler or process in the loop (AGENTS.md §6.2).

Until the discovery-source adapters land there is nothing new to fetch, so the
poll clears the **fit-score backlog**: for **every** search profile it scores each
posting that profile has not scored yet, so each profile has a complete ranked
queue ready the instant the user switches to it (PROJECT.md §2.1, §5.6). Before
scoring a (posting, profile) pair the poll **claims** it (the §4.1 "owned by"
lease, :mod:`atlas.matching.claims`) so a concurrent writer never double-scores.
Scoring is **best-effort per posting** — a posting that can't be scored (no master
resume, or an AI failure) is counted and skipped rather than aborting the batch.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel

from atlas.matching.claims import release_claim, try_claim
from atlas.matching.errors import MatchingError
from atlas.matching.repository import list_unscored_postings
from atlas.matching.service import score_posting
from atlas.profiles.repository import list_profiles
from atlas.resume.service import utcnow

if TYPE_CHECKING:
    from collections.abc import Callable
    from datetime import datetime

    from sqlmodel import Session

    from atlas.ai.base import LLMProvider

__all__ = ["PollOutcome", "run_scoring_poll"]


class PollOutcome(BaseModel):
    """The result of one scoring poll.

    Attributes:
        scored: How many (posting, profile) pairs were successfully scored.
        skipped: How many pairs could not be scored (no master resume / AI
            failure) and were left for a later run.
        claimed: How many pairs were skipped because another worker holds a live
            claim on them (avoiding double work, PROJECT.md §4.1).
    """

    scored: int
    skipped: int
    claimed: int = 0


def run_scoring_poll(
    session: Session,
    *,
    provider: LLMProvider,
    owner: str,
    clock: Callable[[], datetime] = utcnow,
) -> PollOutcome:
    """Score every profile's backlog, best-effort, claiming each pair first.

    For each search profile, scores every posting that profile has not scored yet.
    Each (posting, profile) pair is claimed (:func:`atlas.matching.claims.try_claim`)
    before scoring and released after; a pair another worker holds live is skipped.

    Args:
        session: The open session/transaction to work within.
        provider: The AI backend (or failover chain) to score with.
        owner: This worker's claim token (the daemon process's pid, as a string).
        clock: The clock for each score's ``created_at`` and claim timestamps
            (injectable for tests).

    Returns:
        A :class:`PollOutcome` with the scored / skipped / claimed counts.
    """
    scored = 0
    skipped = 0
    claimed = 0
    for profile in list_profiles(session):
        assert profile.id is not None  # persisted rows always have an id
        for posting in list_unscored_postings(session, profile.id):
            assert posting.id is not None  # persisted rows always have an id
            if not try_claim(
                session,
                job_posting_id=posting.id,
                profile_id=profile.id,
                owner=owner,
                now=clock(),
            ):
                # Another worker is scoring this pair — leave it to them.
                claimed += 1
                continue
            try:
                score_posting(session, posting.id, profile=profile, provider=provider, clock=clock)
            except MatchingError:
                # No master resume / AI failure — leave this pair for a later poll
                # rather than aborting the whole batch.
                skipped += 1
            else:
                scored += 1
            finally:
                release_claim(session, job_posting_id=posting.id, profile_id=profile.id)
    return PollOutcome(scored=scored, skipped=skipped, claimed=claimed)
