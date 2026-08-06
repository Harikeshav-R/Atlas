"""Best-effort desktop-notification dispatch (PROJECT.md §5.16).

Notifications are advisory: a dead or misbehaving notification backend must never
break the daemon's poll. This mirrors the daemon's progress seam
(:func:`atlas.daemon.progress.emit_progress`) — :func:`notify_best_effort` no-ops
on a ``None`` notifier and logs-and-swallows any failure so the caller can fire
and forget.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from atlas.platform.notifier import Notifier

__all__ = ["notify_best_effort"]

_LOGGER = logging.getLogger(__name__)


def notify_best_effort(notifier: Notifier | None, title: str, message: str) -> None:
    """Post a notification through ``notifier`` if one was given, best-effort.

    A ``None`` notifier is a no-op (notifications disabled / unavailable). A
    notifier that raises is logged and swallowed, never propagated — a desktop
    notification failing (no D-Bus, an unsigned macOS interpreter, …) is not a
    poll failure.
    """
    if notifier is None:
        return
    try:
        notifier(title, message)
    except Exception:
        # A desktop-notification backend dying is not a poll failure — log
        # (without the notification text) and carry on.
        _LOGGER.debug("Notifier raised; ignoring.", exc_info=True)
