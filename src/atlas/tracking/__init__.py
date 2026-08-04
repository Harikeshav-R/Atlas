"""Application tracking — status state machine and history (PROJECT.md §5.12).

Every posting the user prepares materials for is an
:class:`~atlas.db.models.Application` that moves through a pipeline of stages.
This package owns the behavior on top of that table (the schema landed with
tailoring): the pure state machine (:mod:`atlas.tracking.status`), the
transition-orchestration service that records timestamped history
(:mod:`atlas.tracking.service`), the listing query the tracking views need
(:mod:`atlas.tracking.repository`), and the package error hierarchy
(:mod:`atlas.tracking.errors`).
"""

from __future__ import annotations

from atlas.tracking.errors import InvalidStatusTransitionError, TrackingError
from atlas.tracking.repository import list_applications
from atlas.tracking.service import (
    StatusChangeOutcome,
    mark_applied,
    set_application_status,
)
from atlas.tracking.status import (
    ALLOWED_TRANSITIONS,
    TERMINAL_STATUSES,
    ApplicationStatus,
    StatusTransition,
    can_transition,
)

__all__ = [
    "ALLOWED_TRANSITIONS",
    "TERMINAL_STATUSES",
    "ApplicationStatus",
    "InvalidStatusTransitionError",
    "StatusChangeOutcome",
    "StatusTransition",
    "TrackingError",
    "can_transition",
    "list_applications",
    "mark_applied",
    "set_application_status",
]
