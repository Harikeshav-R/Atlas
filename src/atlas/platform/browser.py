"""The URL-open boundary — launch a URL in the OS default browser.

Opening a URL in the user's browser is an OS-specific, injectable boundary — like
the file-open boundary (:mod:`atlas.platform.opener`) and the scraper's
:class:`~atlas.scrape.fetcher.Fetcher` — so the default test suite stays hermetic
(no real browser is launched, AGENTS.md §6.2). Callers depend on the
:class:`UrlOpener` protocol; production wiring uses :func:`default_url_opener`
(``webbrowser.open``), and tests inject a fake that records the URLs it was asked
to open.

This is distinct from the file opener: :func:`default_file_opener` requires the
target to exist on disk, whereas the TUI Discover queue's "open" action launches a
posting's *apply URL* in a browser.
"""

from __future__ import annotations

import webbrowser
from typing import Protocol, runtime_checkable

__all__ = ["UrlOpenError", "UrlOpener", "default_url_opener"]


class UrlOpenError(Exception):
    """Raised when a URL cannot be opened in a browser.

    Carries a secret-free, human-readable message for the caller to surface.
    """


@runtime_checkable
class UrlOpener(Protocol):
    """Callable that opens a URL in the OS default browser.

    Implementations raise :class:`UrlOpenError` when no browser could be launched.
    """

    def __call__(self, url: str) -> None:
        """Open ``url`` in the default browser."""


def default_url_opener(url: str) -> None:  # pragma: no cover - launches a real browser
    """Open ``url`` in the OS default browser via :func:`webbrowser.open`.

    Carries ``# pragma: no cover`` because the default test suite never launches a
    real browser (AGENTS.md §6.2); the open flow is exercised through an injected
    fake instead.

    Raises:
        UrlOpenError: If no browser could be launched (``webbrowser.open`` returned
            ``False``) or the platform raised while trying.
    """
    try:
        opened = webbrowser.open(url)
    except webbrowser.Error as exc:
        raise UrlOpenError(f"Could not open {url}: {exc}") from exc
    if not opened:
        raise UrlOpenError(f"Could not open {url}: no browser available.")
