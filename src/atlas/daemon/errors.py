"""Error hierarchy for the Atlas background daemon.

Mirrors :mod:`atlas.tailor.errors`: a package base error plus specific
lifecycle errors carrying a clear, secret-free message for the CLI to surface.
"""

from __future__ import annotations

__all__ = [
    "DaemonAlreadyRunningError",
    "DaemonError",
    "DaemonNotRunningError",
    "IpcError",
    "IpcProtocolError",
    "IpcUnavailableError",
]


class DaemonError(Exception):
    """Base class for every error raised by :mod:`atlas.daemon`."""


class DaemonAlreadyRunningError(DaemonError):
    """Raised when starting the daemon while a live instance already runs.

    Carries the running :attr:`pid` so the CLI can point the user at it.
    """

    def __init__(self, pid: int) -> None:
        """Store the running pid and build a human-readable message."""
        self.pid = pid
        super().__init__(f"The daemon is already running (pid {pid}).")


class DaemonNotRunningError(DaemonError):
    """Raised when stopping the daemon but no live instance is running."""

    def __init__(self) -> None:
        """Build a human-readable message."""
        super().__init__("The daemon is not running.")


class IpcError(DaemonError):
    """Base class for the daemon's local IPC surface errors (PROJECT.md §4.1)."""


class IpcProtocolError(IpcError):
    """Raised when an IPC message cannot be decoded (malformed / unknown shape).

    Carries a secret-free, human-readable message; the transport catches this so
    garbled bytes from one connection never crash the daemon's accept loop.
    """


class IpcUnavailableError(IpcError):
    """Raised when an IPC client cannot reach the daemon.

    The daemon is not running, or its socket is missing/unreachable — a normal,
    recoverable condition the CLI/TUI reports with a fix hint, not a crash.
    """

    def __init__(self) -> None:
        """Build a human-readable message."""
        super().__init__("The daemon is not running or its socket is unavailable.")
