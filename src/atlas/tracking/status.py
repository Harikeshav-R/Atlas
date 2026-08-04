"""The application status state machine (PROJECT.md §5.12).

An :class:`~atlas.db.models.Application` moves through a pipeline of stages —
``Saved → Preparing → Ready → Applied → OA → Interview → Offer / Rejected /
Withdrawn / Ghosted``. This module owns the **pure** rules for that machine:

- :class:`ApplicationStatus` — the closed set of stages, a ``StrEnum`` (mirroring
  :class:`atlas.matching.structure.Verdict`) whose ``.value`` persists into the
  existing ``application.status`` string column.
- :data:`ALLOWED_TRANSITIONS` — the forward-leaning transition graph, and
  :func:`can_transition` — a pure lookup over it. The mutation service
  (:mod:`atlas.tracking.service`) enforces this unless the caller forces an
  override (``atlas status set --force``).
- :data:`TERMINAL_STATUSES` — the stages an application ends in.
- :class:`StatusTransition` — the typed shape of one ``status_history`` entry, so
  history rows serialize consistently into the JSON column.

Nothing here touches the database or the clock; the service layer applies these
rules within a transaction and stamps timestamps from an injected clock.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel

__all__ = [
    "ALLOWED_TRANSITIONS",
    "TERMINAL_STATUSES",
    "ApplicationStatus",
    "StatusTransition",
    "can_transition",
]


class ApplicationStatus(StrEnum):
    """A stage in the application pipeline (PROJECT.md §5.12).

    The ``.value`` is what persists into the ``application.status`` column, so an
    existing row created by tailoring (default ``"preparing"``) already reads back
    as :attr:`PREPARING`.
    """

    SAVED = "saved"
    PREPARING = "preparing"
    READY = "ready"
    APPLIED = "applied"
    OA = "oa"
    INTERVIEW = "interview"
    OFFER = "offer"
    REJECTED = "rejected"
    WITHDRAWN = "withdrawn"
    GHOSTED = "ghosted"


#: The stages an application ends in — no outgoing transitions (only ``--force``
#: escapes them). Reaching one records it as the application's ``outcome``.
TERMINAL_STATUSES: frozenset[ApplicationStatus] = frozenset(
    {
        ApplicationStatus.OFFER,
        ApplicationStatus.REJECTED,
        ApplicationStatus.WITHDRAWN,
        ApplicationStatus.GHOSTED,
    }
)

#: The forward-leaning transition graph. ``Withdrawn`` is reachable from every
#: non-terminal stage (the user can always abandon), and ``Interview`` has a
#: self-edge for successive rounds. Terminal stages map to an empty set, so
#: leaving one requires ``--force``.
ALLOWED_TRANSITIONS: dict[ApplicationStatus, frozenset[ApplicationStatus]] = {
    ApplicationStatus.SAVED: frozenset({ApplicationStatus.PREPARING, ApplicationStatus.WITHDRAWN}),
    ApplicationStatus.PREPARING: frozenset({ApplicationStatus.READY, ApplicationStatus.WITHDRAWN}),
    ApplicationStatus.READY: frozenset({ApplicationStatus.APPLIED, ApplicationStatus.WITHDRAWN}),
    ApplicationStatus.APPLIED: frozenset(
        {
            ApplicationStatus.OA,
            ApplicationStatus.INTERVIEW,
            ApplicationStatus.OFFER,
            ApplicationStatus.REJECTED,
            ApplicationStatus.GHOSTED,
            ApplicationStatus.WITHDRAWN,
        }
    ),
    ApplicationStatus.OA: frozenset(
        {
            ApplicationStatus.INTERVIEW,
            ApplicationStatus.OFFER,
            ApplicationStatus.REJECTED,
            ApplicationStatus.GHOSTED,
            ApplicationStatus.WITHDRAWN,
        }
    ),
    ApplicationStatus.INTERVIEW: frozenset(
        {
            ApplicationStatus.INTERVIEW,
            ApplicationStatus.OFFER,
            ApplicationStatus.REJECTED,
            ApplicationStatus.GHOSTED,
            ApplicationStatus.WITHDRAWN,
        }
    ),
    ApplicationStatus.OFFER: frozenset(),
    ApplicationStatus.REJECTED: frozenset(),
    ApplicationStatus.WITHDRAWN: frozenset(),
    ApplicationStatus.GHOSTED: frozenset(),
}


def can_transition(current: ApplicationStatus, target: ApplicationStatus) -> bool:
    """Return whether moving from ``current`` to ``target`` is allowed.

    A pure lookup over :data:`ALLOWED_TRANSITIONS`; the service uses it to reject
    illegal jumps unless the caller passes ``force=True``.
    """
    return target in ALLOWED_TRANSITIONS[current]


class StatusTransition(BaseModel):
    """One timestamped entry in an application's ``status_history``.

    Serialized into the JSON ``status_history`` column via
    ``model_dump(mode="json")`` so the :class:`~datetime.datetime` fields become
    ISO-8601 strings, and read back with :meth:`~pydantic.BaseModel.model_validate`.

    Attributes:
        from_status: The stage the application was in before the transition.
        to_status: The stage it moved to.
        at: When the transition happened (timezone-aware UTC).
        forced: Whether the transition bypassed the state machine (``--force``).
        due: An optional advisory deadline recorded with the transition (e.g. an
            OA/interview date); real calendar integration is a later phase.
        note: An optional free-form note attached to the transition.
    """

    from_status: str
    to_status: str
    at: datetime
    forced: bool = False
    due: datetime | None = None
    note: str | None = None
