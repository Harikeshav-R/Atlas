"""Persistence for cover letters (PROJECT.md §5.8, §6).

Like :mod:`atlas.tailor.repository`, these are thin, pure functions over an
**open** :class:`~sqlmodel.Session`: the caller opens the transaction with
:func:`atlas.db.session.session_scope`, calls one or more of these, and the scope
commits (or rolls back) on exit. Nothing here opens its own session or engine.

:func:`create_cover_letter` is **append-only and versioned per application**: each
call inserts a new row with the next version number, preserving history — mirroring
:func:`atlas.tailor.repository.create_tailored_resume`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlmodel import col, desc, func, select

from atlas.db.models import CoverLetter

if TYPE_CHECKING:
    from datetime import datetime

    from sqlmodel import Session

__all__ = ["create_cover_letter", "get_latest_cover_letter"]


def create_cover_letter(
    session: Session,
    *,
    application_id: int,
    content: dict[str, Any],
    tone: str,
    rendered_pdf_ref: str | None,
    created_at: datetime,
) -> CoverLetter:
    """Insert a new cover letter for ``application_id`` and return it.

    The new row's ``version`` is one above the current maximum for the application
    (starting at 1), so cover letters are append-only and versioned.

    Args:
        session: The open session/transaction to write within.
        application_id: The owning application.
        content: The structured letter (greeting / hook / body / close) as JSON.
        tone: The tone the letter was written in.
        rendered_pdf_ref: On-disk path to the rendered PDF, if written.
        created_at: When this cover letter was created (timezone-aware UTC).

    Returns:
        The created :class:`~atlas.db.models.CoverLetter`.
    """
    current_max = session.exec(
        select(func.max(CoverLetter.version)).where(CoverLetter.application_id == application_id)
    ).one()
    version = (current_max or 0) + 1
    letter = CoverLetter(
        application_id=application_id,
        content=dict(content),
        tone=tone,
        rendered_pdf_ref=rendered_pdf_ref,
        version=version,
        created_at=created_at,
    )
    session.add(letter)
    session.flush()
    return letter


def get_latest_cover_letter(session: Session, application_id: int) -> CoverLetter | None:
    """Return the most recent cover letter for ``application_id``, or ``None``."""
    return session.exec(
        select(CoverLetter)
        .where(CoverLetter.application_id == application_id)
        .order_by(desc(col(CoverLetter.version)))
    ).first()
