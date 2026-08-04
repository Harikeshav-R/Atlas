"""Error hierarchy for the Atlas application-tracking package.

Mirrors :mod:`atlas.tailor.errors`: a package base error plus a specific
transition error carrying enough context for the CLI to render a clear,
secret-free message. Application lookups reuse
:class:`atlas.tailor.errors.ApplicationNotFoundError`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from atlas.tracking.status import ApplicationStatus

__all__ = [
    "InvalidStatusTransitionError",
    "TrackingError",
]


class TrackingError(Exception):
    """Base class for every error raised by :mod:`atlas.tracking`."""


class InvalidStatusTransitionError(TrackingError):
    """Raised when a status change is not a permitted state-machine transition.

    Carries the :attr:`current` and :attr:`target` stages so the CLI can render a
    specific message and hint that ``--force`` overrides the machine.
    """

    def __init__(self, current: ApplicationStatus, target: ApplicationStatus) -> None:
        """Store the stages and build a human-readable message with a fix hint."""
        self.current = current
        self.target = target
        super().__init__(
            f"Cannot move an application from '{current.value}' to '{target.value}' "
            f"(use --force to override)."
        )
