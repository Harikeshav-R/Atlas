"""Scoring-lease claims for the "owned by" convention (PROJECT.md §4.1).

The daemon's score-every-profile poll scores each (posting, profile) pair. To
avoid double work if a second writer ever runs concurrently, a worker **claims** a
pair here before scoring it (:func:`try_claim`) and releases it after
(:func:`release_claim`). A claim younger than the lease is *live* — another worker
that finds one skips the pair; a claim older than the lease is treated as abandoned
(a crashed worker) and may be stolen.

Pure functions over an **open** :class:`~sqlmodel.Session` (like the rest of the
repository layer), with the clock and lease injected so the logic is deterministic
in tests (AGENTS.md §6.2). The daemon is the single scoring writer, so these are
get-or-create in code; the ``score_claim`` unique constraint on
``(job_posting_id, profile_id)`` documents the invariant and backstops a stray
second writer.
"""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING

from sqlmodel import select

from atlas.db.models import ScoreClaim

if TYPE_CHECKING:
    from datetime import datetime

    from sqlmodel import Session

__all__ = ["DEFAULT_LEASE_SECONDS", "release_claim", "try_claim"]

#: How long a claim stays *live* before it is considered abandoned and reclaimable.
#: Comfortably longer than one posting's scoring call (a single AI round-trip).
DEFAULT_LEASE_SECONDS = 600


def try_claim(
    session: Session,
    *,
    job_posting_id: int,
    profile_id: int,
    owner: str,
    now: datetime,
    lease_seconds: int = DEFAULT_LEASE_SECONDS,
) -> bool:
    """Claim ``(job_posting_id, profile_id)`` for ``owner``; return whether we hold it.

    Returns ``True`` when the pair had no claim (a fresh claim is inserted) or its
    existing claim is **stale** — older than ``lease_seconds`` — in which case the
    claim is stolen (its ``owner``/``claimed_at`` are overwritten). Returns
    ``False`` when a **live** claim is already held (by this or another owner),
    signalling the caller to skip the pair this pass.

    Args:
        session: The open session/transaction to work within.
        job_posting_id: The posting to claim.
        profile_id: The profile the posting is being scored for.
        owner: An opaque owner token (the daemon process's pid).
        now: The current time (injected; timezone-aware UTC).
        lease_seconds: How long a claim stays live before it can be stolen.
    """
    existing = session.exec(
        select(ScoreClaim)
        .where(ScoreClaim.job_posting_id == job_posting_id)
        .where(ScoreClaim.profile_id == profile_id)
    ).first()
    if existing is None:
        session.add(
            ScoreClaim(
                job_posting_id=job_posting_id,
                profile_id=profile_id,
                owner=owner,
                claimed_at=now,
            )
        )
        session.flush()
        return True
    if now - existing.claimed_at >= timedelta(seconds=lease_seconds):
        # The prior claim is stale (a crashed/slow worker) — steal it.
        existing.owner = owner
        existing.claimed_at = now
        session.add(existing)
        session.flush()
        return True
    return False


def release_claim(session: Session, *, job_posting_id: int, profile_id: int) -> None:
    """Release any claim on ``(job_posting_id, profile_id)`` (a no-op if none).

    Called after a pair is scored so the row does not linger; missing claims are
    tolerated so a double release (or a released-then-expired claim) is harmless.
    """
    existing = session.exec(
        select(ScoreClaim)
        .where(ScoreClaim.job_posting_id == job_posting_id)
        .where(ScoreClaim.profile_id == profile_id)
    ).first()
    if existing is not None:
        session.delete(existing)
        session.flush()
