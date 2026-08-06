"""Cross-platform application paths for Atlas.

All config/data/cache/state locations resolve through :mod:`platformdirs` so
Atlas is a first-class citizen on Windows, macOS, and Linux without hardcoding
``~/.config`` (PROJECT.md §12.1). These helpers are pure — they compute paths and
never create directories or touch the filesystem.
"""

from __future__ import annotations

from pathlib import Path

import platformdirs

__all__ = [
    "cache_dir",
    "config_dir",
    "config_file",
    "data_dir",
    "notify_state_file",
    "pid_file",
    "socket_file",
    "state_dir",
]

#: The application name used for every platformdirs lookup.
_APP_NAME = "atlas"

#: The daemon's PID file name, under the state dir.
_PID_FILENAME = "daemon.pid"

#: The daemon's IPC socket file name, under the state dir.
_SOCKET_FILENAME = "daemon.socket"

#: The desktop-notification run-state file name, under the state dir.
_NOTIFY_STATE_FILENAME = "notify-state.json"


def config_dir() -> Path:
    """Return the directory that holds Atlas's config (``config.toml`` lives here)."""
    return Path(platformdirs.user_config_dir(_APP_NAME))


def data_dir() -> Path:
    """Return the directory for Atlas's data files (resumes, PDFs, snapshots, DB)."""
    return Path(platformdirs.user_data_dir(_APP_NAME))


def cache_dir() -> Path:
    """Return the directory for Atlas's disposable cache files."""
    return Path(platformdirs.user_cache_dir(_APP_NAME))


def state_dir() -> Path:
    """Return the directory for Atlas's state files (logs, run state)."""
    return Path(platformdirs.user_state_dir(_APP_NAME))


def config_file() -> Path:
    """Return the path to the main ``config.toml`` inside :func:`config_dir`."""
    return config_dir() / "config.toml"


def pid_file() -> Path:
    """Return the path to the daemon's PID file inside :func:`state_dir`."""
    return state_dir() / _PID_FILENAME


def socket_file() -> Path:
    """Return the path to the daemon's IPC socket inside :func:`state_dir`.

    The daemon's local IPC surface (PROJECT.md §4.1) binds here so the TUI/CLI can
    trigger on-demand work; on POSIX it is the Unix-domain-socket node, on Windows
    a sidecar file recording the loopback port. Pure — like the sibling path
    helpers, it computes the path and never touches the filesystem.
    """
    return state_dir() / _SOCKET_FILENAME


def notify_state_file() -> Path:
    """Return the path to the desktop-notification state file in :func:`state_dir`.

    The daemon records its notification run-state here — the high-water mark of
    the last match score it notified about, the day's notification count, and the
    deadline keys already alerted (PROJECT.md §5.16) — so a re-poll never
    re-notifies. Pure — like the sibling path helpers, it computes the path and
    never touches the filesystem.
    """
    return state_dir() / _NOTIFY_STATE_FILENAME
