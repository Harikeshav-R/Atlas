"""The daemon's scheduled scoring poll (PROJECT.md §4.1, §5.6).

This is the daemon's real work, written as a **pure function over an open**
:class:`~sqlmodel.Session` (like the service layer elsewhere) so it is tested
directly with the in-memory ``db_engine`` fixture and a fake provider, with no
scheduler or process in the loop (AGENTS.md §6.2).

Until the discovery-source adapters land there is nothing new to fetch, so the
poll clears the **fit-score backlog**: it scores every posting that has no
:class:`~atlas.db.models.MatchScore` yet against the active profile. Scoring is
**best-effort per posting** — a posting that can't be scored (no active profile,
no master resume, or an AI failure) is counted and skipped rather than aborting
the batch, mirroring the ``_score_after_add`` pattern the ``atlas add`` command
uses.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel

from atlas.matching.errors import MatchingError
from atlas.matching.repository import list_unscored_postings
from atlas.matching.service import score_posting
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
        scored: How many postings were successfully scored this poll.
        skipped: How many unscored postings could not be scored (no active
            profile / no master resume / AI failure) and were left for a later run.
    """

    scored: int
    skipped: int


def run_scoring_poll(
    session: Session,
    *,
    provider: LLMProvider,
    clock: Callable[[], datetime] = utcnow,
) -> PollOutcome:
    """Score every not-yet-scored posting against the active profile, best-effort.

    Args:
        session: The open session/transaction to work within.
        provider: The AI backend (or failover chain) to score with.
        clock: The clock for each score's ``created_at`` (injectable for tests).

    Returns:
        A :class:`PollOutcome` with the scored and skipped counts.
    """
    scored = 0
    skipped = 0
    for posting in list_unscored_postings(session):
        assert posting.id is not None  # persisted rows always have an id
        try:
            score_posting(session, posting.id, provider=provider, clock=clock)
        except MatchingError:
            # No active profile / no master resume / AI failure — leave this
            # posting for a later poll rather than aborting the whole batch.
            skipped += 1
        else:
            scored += 1
    return PollOutcome(scored=scored, skipped=skipped)
