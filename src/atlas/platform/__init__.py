"""OS-specific boundaries behind one interface (PROJECT.md §12.1).

Atlas is cross-platform (Windows / macOS / Linux); every OS-specific call is
isolated behind an injectable boundary so the rest of the code stays OS-agnostic
and the test suite stays hermetic. This package holds the file-open boundary
(:mod:`atlas.platform.opener`) used by ``atlas open``, the URL-open boundary
(:mod:`atlas.platform.browser`) used by the TUI Discover queue, and the
desktop-notification boundary (:mod:`atlas.platform.notifier`) used by the daemon;
further platform concerns (daemon install, …) join them as they land.
"""

from __future__ import annotations

from atlas.platform.browser import UrlOpener, UrlOpenError, default_url_opener
from atlas.platform.notifier import Notifier, NotifyError, default_notifier
from atlas.platform.opener import FileOpener, FileOpenError, default_file_opener

__all__ = [
    "FileOpenError",
    "FileOpener",
    "Notifier",
    "NotifyError",
    "UrlOpenError",
    "UrlOpener",
    "default_file_opener",
    "default_notifier",
    "default_url_opener",
]
