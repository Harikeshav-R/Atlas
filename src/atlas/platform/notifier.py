"""The desktop-notification boundary — post a native OS notification.

Posting a native notification is an OS-specific, injectable boundary — like the
file-open boundary (:mod:`atlas.platform.opener`) and the URL-open boundary
(:mod:`atlas.platform.browser`) — so the default test suite stays hermetic (no
real notification is posted, AGENTS.md §6.2). Callers depend on the
:class:`Notifier` protocol; production wiring uses :func:`default_notifier`
(``desktop-notifier`` over D-Bus / Notification Center / WinRT), and tests inject
a fake that records the notifications it was asked to post.

This is the ``notifier`` piece of the ``platform`` abstraction PROJECT.md §12.1
describes; the daemon fires these for new high-fit matches and upcoming deadlines
even when the TUI is closed (PROJECT.md §4.1, §5.16). Notifications are
**fire-and-forget**: callers post through :func:`atlas.notify.emit.notify_best_effort`,
which swallows any failure so a dead notification backend never breaks a poll.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

__all__ = ["Notifier", "NotifyError", "default_notifier"]

#: The application name shown as the notification source.
_APP_NAME = "Atlas"


class NotifyError(Exception):
    """Raised when a desktop notification cannot be posted.

    Carries a secret-free, human-readable message for the caller to surface.
    """


@runtime_checkable
class Notifier(Protocol):
    """Callable that posts a native desktop notification.

    Implementations raise :class:`NotifyError` when no notification backend is
    usable or posting fails.
    """

    def __call__(self, title: str, message: str) -> None:
        """Post a notification with ``title`` and ``message``."""


def default_notifier(title: str, message: str) -> None:  # pragma: no cover - real notification
    """Post a native notification via ``desktop-notifier``.

    Uses :class:`desktop_notifier.DesktopNotifierSync`, which dispatches to the
    platform backend internally (D-Bus on Linux, Notification Center on macOS,
    WinRT on Windows) and **degrades gracefully** — silently ignoring unsupported
    features rather than raising (PROJECT.md §5.16). The heavy import is lazy so
    the hermetic suite never loads it. This boundary carries ``# pragma: no cover``
    because the default test suite never posts a real notification (AGENTS.md
    §6.2); the post flow is exercised through an injected fake instead.

    On macOS 10.14+ only a signed interpreter may post notifications; under an
    unsigned interpreter posting fails and the best-effort caller swallows it, so
    Atlas still runs (notifications just don't appear).

    Raises:
        NotifyError: If the notification backend could not post the notification.
    """
    from desktop_notifier import DesktopNotifierSync

    try:
        DesktopNotifierSync(app_name=_APP_NAME).send(title=title, message=message)
    except Exception as exc:
        # Any backend failure (no D-Bus, unsigned macOS interpreter, …) maps to
        # the one domain error; the best-effort caller then swallows it.
        raise NotifyError(f"Could not post notification: {exc}") from exc
