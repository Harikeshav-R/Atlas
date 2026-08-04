"""Persistence for applications and tailored resumes (PROJECT.md §5.7, §6).

Like :mod:`atlas.matching.repository`, these are thin, pure functions over an
**open** :class:`~sqlmodel.Session`: the caller opens the transaction with
:func:`atlas.db.session.session_scope`, calls one or more of these, and the scope
commits (or rolls back) on exit. Nothing here opens its own session or engine.

:func:`get_or_create_application` keeps one application per (posting, profile)
— mirroring the get-or-create idiom in :mod:`atlas.scrape.repository`.
:func:`create_tailored_resume` is **append-only and versioned per application**:
each call inserts a new row with the next version number, preserving history.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlmodel import col, desc, func, select

from atlas.db.models import Application, TailoredResume
from atlas.tailor.errors import ApplicationNotFoundError

if TYPE_CHECKING:
    from datetime import datetime

    from sqlmodel import Session

__all__ = [
    "create_tailored_resume",
    "get_application",
    "get_latest_tailored_resume",
    "get_or_create_application",
]


def get_application(session: Session, application_id: int) -> Application:
    """Return the application with ``application_id``.

    Raises:
        ApplicationNotFoundError: If no application has that id.
    """
    application = session.get(Application, application_id)
    if application is None:
        raise ApplicationNotFoundError(application_id)
    return application


def get_or_create_application(
    session: Session,
    *,
    job_posting_id: int,
    profile_id: int,
    clock: datetime,
) -> Application:
    """Return the application for ``(job_posting_id, profile_id)``, creating one if absent.

    Deduplicated by (posting, profile) in code so re-tailoring a posting reuses its
    application rather than inserting a duplicate. A freshly created application
    starts in ``preparing`` with empty history.

    Args:
        session: The open session/transaction to write within.
        job_posting_id: The posting the application is for.
        profile_id: The profile the application is prepared under.
        clock: The timestamp for a newly created application's created/updated.

    Returns:
        The existing or newly created :class:`~atlas.db.models.Application`.
    """
    existing = session.exec(
        select(Application).where(
            Application.job_posting_id == job_posting_id,
            Application.profile_id == profile_id,
        )
    ).first()
    if existing is not None:
        return existing
    application = Application(
        job_posting_id=job_posting_id,
        profile_id=profile_id,
        created_at=clock,
        updated_at=clock,
    )
    session.add(application)
    session.flush()
    return application


def create_tailored_resume(
    session: Session,
    *,
    application_id: int,
    master_resume_version: int,
    selections: list[dict[str, Any]],
    final_content: dict[str, Any],
    rendered_pdf_ref: str | None,
    decisions: list[dict[str, Any]],
    created_at: datetime,
) -> TailoredResume:
    """Insert a new tailored resume for ``application_id`` and return it.

    The new row's ``version`` is one above the current maximum for the
    application (starting at 1), so tailored resumes are append-only and versioned.

    Args:
        session: The open session/transaction to write within.
        application_id: The owning application.
        master_resume_version: The master-resume version the content was drawn from.
        selections: The content-ID'd selection items, as JSON.
        final_content: The rendered resume view-model snapshot, as JSON.
        rendered_pdf_ref: On-disk path to the rendered PDF, if written.
        decisions: The include/exclude/reword rationale per item, as JSON.
        created_at: When this tailored resume was created (timezone-aware UTC).

    Returns:
        The created :class:`~atlas.db.models.TailoredResume`.
    """
    current_max = session.exec(
        select(func.max(TailoredResume.version)).where(
            TailoredResume.application_id == application_id
        )
    ).one()
    version = (current_max or 0) + 1
    tailored = TailoredResume(
        application_id=application_id,
        master_resume_version=master_resume_version,
        selections=list(selections),
        final_content=dict(final_content),
        rendered_pdf_ref=rendered_pdf_ref,
        decisions=list(decisions),
        version=version,
        created_at=created_at,
    )
    session.add(tailored)
    session.flush()
    return tailored


def get_latest_tailored_resume(session: Session, application_id: int) -> TailoredResume | None:
    """Return the most recent tailored resume for ``application_id``, or ``None``."""
    return session.exec(
        select(TailoredResume)
        .where(TailoredResume.application_id == application_id)
        .order_by(desc(col(TailoredResume.version)))
    ).first()
