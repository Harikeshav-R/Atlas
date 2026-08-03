"""Persistence for fit scores (PROJECT.md §5.6, §6).

Like :mod:`atlas.scrape.repository`, these are thin, pure functions over an
**open** :class:`~sqlmodel.Session`: the caller opens the transaction with
:func:`atlas.db.session.session_scope`, calls one or more of these, and the scope
commits (or rolls back) on exit. Nothing here opens its own session or engine.

Scores are **append-only** (see :class:`~atlas.db.models.MatchScore`):
:func:`create_match_score` always inserts a new row, and
:func:`get_latest_match_score` returns the most recent one for a posting, so
re-scoring preserves history while the queue shows the latest assessment.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlmodel import col, desc, select

from atlas.db.models import MatchScore

if TYPE_CHECKING:
    from datetime import datetime

    from sqlmodel import Session

__all__ = ["create_match_score", "get_latest_match_score"]


def create_match_score(
    session: Session,
    *,
    job_posting_id: int,
    profile_id: int,
    score: int,
    verdict: str,
    rationale: str,
    matched_strengths: list[str],
    gaps: list[str],
    dealbreaker_hits: list[str],
    salary_fit: str,
    signals: dict[str, Any],
    model: str,
    created_at: datetime,
) -> MatchScore:
    """Insert a new :class:`~atlas.db.models.MatchScore` and return it (id assigned).

    Always inserts (append-only): re-scoring a posting adds a new row rather than
    mutating an earlier one.

    Args:
        session: The open session/transaction to write within.
        job_posting_id: The scored posting's id.
        profile_id: The profile the posting was scored against.
        score: The AI fit score, 0-100.
        verdict: The AI verdict.
        rationale: The AI's explanation of the score.
        matched_strengths: Strengths the posting matches.
        gaps: Missing keywords/skills/requirements.
        dealbreaker_hits: Deal-breakers the posting triggers.
        salary_fit: The AI salary verdict.
        signals: The computed deterministic signals as a JSON object.
        model: The AI model that produced the assessment.
        created_at: When the assessment was created (timezone-aware UTC).

    Returns:
        The created :class:`~atlas.db.models.MatchScore`.
    """
    match_score = MatchScore(
        job_posting_id=job_posting_id,
        profile_id=profile_id,
        score=score,
        verdict=verdict,
        rationale=rationale,
        matched_strengths=list(matched_strengths),
        gaps=list(gaps),
        dealbreaker_hits=list(dealbreaker_hits),
        salary_fit=salary_fit,
        signals=dict(signals),
        model=model,
        created_at=created_at,
    )
    session.add(match_score)
    session.flush()
    return match_score


def get_latest_match_score(session: Session, job_posting_id: int) -> MatchScore | None:
    """Return the most recent score for ``job_posting_id``, or ``None`` if unscored.

    Ordered by insertion (id) descending, so the newest append-only row wins.
    """
    return session.exec(
        select(MatchScore)
        .where(MatchScore.job_posting_id == job_posting_id)
        .order_by(desc(col(MatchScore.id)))
    ).first()
