"""Persistence queries for application tracking (PROJECT.md §5.12, §6).

Like :mod:`atlas.tailor.repository`, these are thin, pure functions over an
**open** :class:`~sqlmodel.Session`: the caller opens the transaction with
:func:`atlas.db.session.session_scope`, calls one or more of these, and the scope
commits (or rolls back) on exit. Nothing here opens its own session or engine.

Application lookup by id and the get-or-create used when tailoring first creates
an application live in :mod:`atlas.tailor.repository`; this module adds the
listing query the tracking views (CLI ``atlas list`` and the later TUI) need.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlmodel import col, desc, select

from atlas.db.models import Application

if TYPE_CHECKING:
    from collections.abc import Sequence

    from sqlmodel import Session

    from atlas.tracking.status import ApplicationStatus

__all__ = ["list_applications"]


def list_applications(
    session: Session,
    *,
    status: ApplicationStatus | None = None,
    profile_id: int | None = None,
) -> Sequence[Application]:
    """Return tracked applications, most recently updated first.

    Args:
        session: The open session to read within.
        status: If given, keep only applications currently in that stage.
        profile_id: If given, keep only applications for that profile.

    Returns:
        The matching :class:`~atlas.db.models.Application` rows, ordered by
        :attr:`~atlas.db.models.Application.updated_at` descending (newest first).
    """
    statement = select(Application)
    if status is not None:
        statement = statement.where(Application.status == status.value)
    if profile_id is not None:
        statement = statement.where(Application.profile_id == profile_id)
    statement = statement.order_by(desc(col(Application.updated_at)))
    return session.exec(statement).all()
