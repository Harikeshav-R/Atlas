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

from sqlalchemy.orm import aliased
from sqlmodel import col, desc, func, select

from atlas.db.models import JobPosting, MatchScore
from atlas.matching.structure import QueueStatus

if TYPE_CHECKING:
    from collections.abc import Sequence
    from datetime import datetime

    from sqlmodel import Session

__all__ = [
    "create_match_score",
    "get_latest_match_score",
    "list_scored_postings",
    "list_unscored_postings",
]


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


def get_latest_match_score(
    session: Session, job_posting_id: int, *, profile_id: int | None = None
) -> MatchScore | None:
    """Return the most recent score for ``job_posting_id``, or ``None`` if unscored.

    Ordered by insertion (id) descending, so the newest append-only row wins. When
    ``profile_id`` is given, only that profile's scores are considered (a posting
    now carries one score history per profile); the default (``None``) keeps the
    profile-agnostic "latest score by any profile" behaviour for callers that don't
    scope to a profile.
    """
    statement = select(MatchScore).where(MatchScore.job_posting_id == job_posting_id)
    if profile_id is not None:
        statement = statement.where(MatchScore.profile_id == profile_id)
    return session.exec(statement.order_by(desc(col(MatchScore.id)))).first()


def list_unscored_postings(session: Session, profile_id: int) -> Sequence[JobPosting]:
    """Return postings not yet scored **for ``profile_id``**.

    The background daemon's scoring poll (PROJECT.md §4.1, §5.6) uses this to find
    one profile's fit-score backlog. A posting counts as scored *for a profile* once
    it has at least one (append-only) match-score row for that profile, so it drops
    out of this list after its first successful score against ``profile_id`` — but
    stays in every other profile's backlog until scored there too. Ordered by
    insertion (id) for a stable, oldest-first poll order.
    """
    scored = select(MatchScore.job_posting_id).where(MatchScore.profile_id == profile_id)
    return session.exec(
        select(JobPosting).where(col(JobPosting.id).not_in(scored)).order_by(col(JobPosting.id))
    ).all()


def list_scored_postings(
    session: Session, profile_id: int
) -> Sequence[tuple[JobPosting, MatchScore]]:
    """Return ``profile_id``'s scored, non-dismissed postings, ranked by fit.

    The TUI Discover queue (PROJECT.md §8 screen #2) uses this: each row is a
    posting paired with its **latest** :class:`~atlas.db.models.MatchScore` **for
    ``profile_id``** — the row with the greatest ``id`` for that (posting, profile)
    pair, matching :func:`get_latest_match_score`'s "newest append-only row wins"
    convention (not ``created_at``). Postings this profile has not scored are
    excluded (an inner match), and ``dismissed`` postings are hidden. Ordered by
    score descending, then newest posting first (``JobPosting.id`` descending) as a
    stable tiebreak.
    """
    inner = aliased(MatchScore)
    latest_id = (
        select(func.max(inner.id))
        .where(inner.job_posting_id == JobPosting.id)
        .where(inner.profile_id == profile_id)
        .correlate(JobPosting)
        .scalar_subquery()
    )
    rows = session.exec(
        select(JobPosting, MatchScore)
        .where(MatchScore.job_posting_id == JobPosting.id)
        .where(MatchScore.profile_id == profile_id)
        .where(MatchScore.id == latest_id)
        .where(JobPosting.queue_status != QueueStatus.DISMISSED)
        .order_by(desc(col(MatchScore.score)), desc(col(JobPosting.id)))
    ).all()
    return [(posting, score) for posting, score in rows]
