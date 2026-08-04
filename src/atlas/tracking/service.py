"""Application status-transition orchestration (PROJECT.md §5.12, §9).

The domain layer between the CLI (``atlas status set`` / ``atlas apply mark``) and
the data model. It applies the pure state machine (:mod:`atlas.tracking.status`)
over an **open** :class:`~sqlmodel.Session`, records each change as a timestamped
``status_history`` entry, and stamps :attr:`~atlas.db.models.Application.applied_at`
/ :attr:`~atlas.db.models.Application.outcome` / ``updated_at`` as the machine
dictates.

Neither function opens its own transaction (the caller wraps them in
:func:`atlas.db.session.session_scope`); the clock is injected (defaulting to
:func:`atlas.resume.service.utcnow`) so persisted timestamps are deterministic in
tests. Application lookup reuses :func:`atlas.tailor.repository.get_application`,
so an unknown id raises :class:`~atlas.tailor.errors.ApplicationNotFoundError`.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from pydantic import BaseModel

from atlas.resume.service import utcnow
from atlas.tailor.repository import get_application
from atlas.tracking.errors import InvalidStatusTransitionError
from atlas.tracking.status import (
    TERMINAL_STATUSES,
    ApplicationStatus,
    StatusTransition,
    can_transition,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from sqlmodel import Session

__all__ = [
    "StatusChangeOutcome",
    "mark_applied",
    "set_application_status",
]


class StatusChangeOutcome(BaseModel):
    """The result of a status transition (``--json``-serializable).

    Attributes:
        application_id: The application whose status changed.
        previous_status: The stage the application was in before the change.
        new_status: The stage it is in now.
        applied_at: When the application was marked applied, if that has happened
            (set the moment the application first reaches :attr:`ApplicationStatus.APPLIED`).
        outcome: The final outcome, once a terminal stage is reached.
        forced: Whether the transition bypassed the state machine (``--force``).
        due: The advisory deadline recorded with this transition, if any.
    """

    application_id: int
    previous_status: str
    new_status: str
    applied_at: datetime | None
    outcome: str | None
    forced: bool
    due: datetime | None


def set_application_status(
    session: Session,
    application_id: int,
    target: ApplicationStatus,
    *,
    force: bool = False,
    due: datetime | None = None,
    note: str | None = None,
    clock: Callable[[], datetime] = utcnow,
) -> StatusChangeOutcome:
    """Move an application to ``target``, recording the transition.

    Validates the move against the state machine unless ``force`` is set, appends a
    :class:`~atlas.tracking.status.StatusTransition` to the application's history,
    and updates the derived columns: ``applied_at`` when the application first
    reaches :attr:`ApplicationStatus.APPLIED`, and ``outcome`` when it reaches a
    terminal stage. ``updated_at`` is always bumped.

    Args:
        session: The open transaction to write within.
        application_id: The application to transition.
        target: The stage to move to.
        force: Skip the state-machine check and allow any transition.
        due: An optional advisory deadline to record with the transition.
        note: An optional free-form note to record with the transition.
        clock: The clock used to timestamp the transition (injected for tests).

    Returns:
        A :class:`StatusChangeOutcome` describing the change.

    Raises:
        ApplicationNotFoundError: If no application has ``application_id``.
        InvalidStatusTransitionError: If the move is not permitted and ``force``
            is not set.
    """
    application = get_application(session, application_id)
    assert application.id is not None  # persisted rows always have an id

    current = ApplicationStatus(application.status)
    if not force and not can_transition(current, target):
        raise InvalidStatusTransitionError(current, target)

    now = clock()
    transition = StatusTransition(
        from_status=current.value,
        to_status=target.value,
        at=now,
        forced=force,
        due=due,
        note=note,
    )
    # Reassign a new list so SQLAlchemy marks the JSON column dirty (mutating the
    # existing list in place would not be detected).
    application.status_history = [
        *application.status_history,
        transition.model_dump(mode="json"),
    ]
    application.status = target.value
    application.updated_at = now
    if target is ApplicationStatus.APPLIED and application.applied_at is None:
        application.applied_at = now
    if target in TERMINAL_STATUSES:
        application.outcome = target.value

    session.add(application)
    session.flush()

    return StatusChangeOutcome(
        application_id=application.id,
        previous_status=current.value,
        new_status=target.value,
        applied_at=application.applied_at,
        outcome=application.outcome,
        forced=force,
        due=due,
    )


def mark_applied(
    session: Session,
    application_id: int,
    *,
    force: bool = False,
    clock: Callable[[], datetime] = utcnow,
) -> StatusChangeOutcome:
    """Mark an application submitted (``atlas apply mark``).

    A convenience over :func:`set_application_status` that moves the application to
    :attr:`ApplicationStatus.APPLIED`, recording ``applied_at``.

    Raises:
        ApplicationNotFoundError: If no application has ``application_id``.
        InvalidStatusTransitionError: If the application cannot move to ``applied``
            from its current stage and ``force`` is not set.
    """
    return set_application_status(
        session,
        application_id,
        ApplicationStatus.APPLIED,
        force=force,
        clock=clock,
    )
