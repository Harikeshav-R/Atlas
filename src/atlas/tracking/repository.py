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

from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from pydantic import BaseModel
from sqlmodel import col, desc, func, select

from atlas.db.models import Application
from atlas.tracking.status import TERMINAL_STATUSES, ApplicationStatus, StatusTransition

if TYPE_CHECKING:
    from collections.abc import Sequence

    from sqlmodel import Session

__all__ = [
    "DeadlineItem",
    "count_applications_by_status",
    "list_applications",
    "upcoming_deadlines",
]


class DeadlineItem(BaseModel):
    """An application deadline coming up within the notification lead window.

    Attributes:
        application_id: The :class:`~atlas.db.models.Application` the deadline is on.
        status: The stage whose transition recorded the deadline (e.g. ``"oa"``,
            ``"interview"``).
        due: When the deadline falls (timezone-aware UTC).
        key: A stable per-deadline key (``"<application_id>:<due-iso>"``) the daemon
            uses to notify about a given deadline exactly once.
    """

    application_id: int
    status: str
    due: datetime
    key: str


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


def count_applications_by_status(
    session: Session,
    *,
    profile_id: int | None = None,
) -> dict[str, int]:
    """Return how many applications sit in each status, keyed by status value.

    The Dashboard's pipeline funnel (PROJECT.md §8) reads this. Only statuses with
    at least one application appear (a stage with none is simply absent), so the
    caller supplies zeros for the stages it wants to show.

    Args:
        session: The open session to read within.
        profile_id: If given, count only applications for that profile.

    Returns:
        A mapping of ``status`` value → count.
    """
    statement = select(Application.status, func.count()).group_by(col(Application.status))
    if profile_id is not None:
        statement = statement.where(Application.profile_id == profile_id)
    return dict(session.exec(statement).all())


def upcoming_deadlines(
    session: Session,
    *,
    now: datetime,
    lead_hours: int,
) -> list[DeadlineItem]:
    """Return deadlines falling within ``lead_hours`` of ``now``, soonest first.

    Deadlines are advisory dates recorded per status transition
    (:attr:`~atlas.tracking.status.StatusTransition.due`) and live only inside the
    JSON ``status_history`` column — there is no queryable deadline column yet
    (real calendar integration is a later phase, PROJECT.md §5.12). This scans the
    history of every **non-terminal** application (a finished application has no
    live deadline), collecting each entry whose ``due`` falls in the half-open
    window ``[now, now + lead_hours)``. A malformed history entry is skipped rather
    than crashing the daemon's notification pass.

    The daemon's desktop notifications (PROJECT.md §5.16) use this; each item's
    stable :attr:`~DeadlineItem.key` lets the daemon alert on a given deadline once.
    """
    horizon = now + timedelta(hours=lead_hours)
    items: list[DeadlineItem] = []
    for application in session.exec(select(Application)).all():
        if application.id is None:  # pragma: no cover - persisted rows always have an id
            continue
        if application.status in {status.value for status in TERMINAL_STATUSES}:
            continue
        for entry in application.status_history:
            try:
                transition = StatusTransition.model_validate(entry)
            except ValueError:
                # A hand-mangled history entry must not sink the whole pass.
                continue
            due = transition.due
            if due is None or not (now <= due < horizon):
                continue
            items.append(
                DeadlineItem(
                    application_id=application.id,
                    status=transition.to_status,
                    due=due,
                    key=f"{application.id}:{due.isoformat()}",
                )
            )
    items.sort(key=lambda item: item.due)
    return items
