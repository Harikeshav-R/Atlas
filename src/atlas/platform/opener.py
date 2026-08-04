"""The file-open boundary — launch a file in the OS default application.

Opening a file in the user's default viewer is an OS-specific, injectable boundary
— like the coding-CLI :class:`~atlas.ai.cli.runner.SubprocessRunner` and the
scraper's :class:`~atlas.scrape.fetcher.Fetcher` — so the default test suite stays
hermetic (no real GUI app is launched, AGENTS.md §6.2). Callers depend on the
:class:`FileOpener` protocol; production wiring uses :func:`default_file_opener`
(which dispatches on ``sys.platform``), and tests inject a fake that records the
paths it was asked to open.

This is the first piece of the ``platform`` abstraction PROJECT.md §12.1 describes
(isolating OS-specific calls — paths, keyring, notifier, daemon install, file-open
— behind one interface); further platform boundaries join it here later.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Protocol, runtime_checkable

__all__ = ["FileOpenError", "FileOpener", "default_file_opener"]


class FileOpenError(Exception):
    """Raised when a file cannot be opened (missing file or launch failure).

    Carries a secret-free, human-readable message for the CLI to surface.
    """


@runtime_checkable
class FileOpener(Protocol):
    """Callable that opens a file in the OS default application.

    Implementations raise :class:`FileOpenError` when the file does not exist or
    the platform launcher fails.
    """

    def __call__(self, path: Path) -> None:
        """Open ``path`` in the default application for its type."""


def default_file_opener(path: Path) -> None:  # pragma: no cover - launches a real GUI app
    """Open ``path`` in the OS default application, dispatching on ``sys.platform``.

    Uses ``os.startfile`` on Windows, ``open`` on macOS, and ``xdg-open`` on Linux
    / other POSIX. This boundary carries ``# pragma: no cover`` because the default
    test suite never launches a real application (AGENTS.md §6.2); the open flow is
    exercised through an injected fake instead.

    Raises:
        FileOpenError: If ``path`` does not exist or the launcher fails.
    """
    if not path.exists():
        raise FileOpenError(f"File does not exist: {path}")
    try:
        if sys.platform == "win32":
            # os.startfile exists only on Windows; the ignore is unused off-win32.
            os.startfile(path)  # type: ignore[attr-defined, unused-ignore]
        else:
            command = "open" if sys.platform == "darwin" else "xdg-open"
            subprocess.run([command, str(path)], check=True)
    except OSError as exc:
        raise FileOpenError(f"Could not open {path}: {exc}") from exc
    except subprocess.CalledProcessError as exc:
        raise FileOpenError(f"Could not open {path}: launcher exited {exc.returncode}") from exc
