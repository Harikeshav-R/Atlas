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
    "pid_file",
    "state_dir",
]

#: The application name used for every platformdirs lookup.
_APP_NAME = "atlas"

#: The daemon's PID file name, under the state dir.
_PID_FILENAME = "daemon.pid"


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
