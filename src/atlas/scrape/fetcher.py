"""The HTTP fetch boundary for the scraper (PROJECT.md §5.5).

Fetching a posting URL is an injectable boundary — like the coding-CLI
:class:`~atlas.ai.cli.runner.SubprocessRunner` — so the default test suite stays
hermetic (no real network, per AGENTS.md §6.2). Callers depend on the
:class:`Fetcher` protocol; production wiring uses :func:`default_fetcher` (a thin
``httpx`` call), and tests inject a fake that replays scripted
:class:`FetchResult` values or raises.

The :class:`BrowserFetcher` protocol is the seam for the future Playwright
headless-Chromium fallback for JS-rendered pages (PROJECT.md §5.5/§13). It is
**not** wired yet — no ``playwright`` dependency exists — but the scrape service
already accepts one and uses it when a static fetch looks JS-rendered, so the
fallback drops in later without reworking the fetch flow.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

import httpx

from atlas.scrape.errors import FetchError

if TYPE_CHECKING:
    from collections.abc import Mapping

__all__ = [
    "BrowserFetcher",
    "FetchResult",
    "Fetcher",
    "default_fetcher",
]

#: The user-agent Atlas identifies itself with (polite fetching, PROJECT.md §5.5).
_USER_AGENT = "Atlas-JobCopilot/0.1 (+https://github.com/Harikeshav-R/Atlas)"


@dataclass(frozen=True)
class FetchResult:
    """The captured outcome of fetching a URL.

    Attributes:
        url: The final URL after any redirects.
        status_code: The HTTP status code.
        content_type: The response ``Content-Type`` header, if any.
        body: The response body decoded as text.
    """

    url: str
    status_code: int
    content_type: str | None
    body: str


@runtime_checkable
class Fetcher(Protocol):
    """Callable that fetches a URL and returns its :class:`FetchResult`.

    Implementations must follow redirects, decode the body as text, and raise
    :class:`~atlas.scrape.errors.FetchError` on a network failure or a
    non-success HTTP status.

    The default is a plain ``GET``; ``method`` / ``json_body`` / ``headers`` are
    optional so an ATS adapter can issue a JSON ``POST`` (e.g. Workday's CxS API)
    over the same seam. Existing callers pass none of these and are unaffected.
    """

    def __call__(
        self,
        url: str,
        *,
        timeout_s: int,
        method: str = "GET",
        json_body: Mapping[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> FetchResult:
        """Fetch ``url`` and return its :class:`FetchResult`."""


@runtime_checkable
class BrowserFetcher(Protocol):
    """Callable that renders a JS-heavy URL in a headless browser (future seam).

    The same shape as :class:`Fetcher`; a Playwright-backed implementation will
    fulfil it in a later step. Injected into the scrape service as an optional
    fallback and consulted only when a static fetch looks JS-rendered.
    """

    def __call__(
        self,
        url: str,
        *,
        timeout_s: int,
        method: str = "GET",
        json_body: Mapping[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> FetchResult:
        """Render ``url`` in a browser and return its :class:`FetchResult`."""


def default_fetcher(
    url: str,
    *,
    timeout_s: int,
    method: str = "GET",
    json_body: Mapping[str, Any] | None = None,
    headers: Mapping[str, str] | None = None,
) -> FetchResult:  # pragma: no cover
    """Fetch ``url`` over HTTP with ``httpx``, following redirects.

    This thin network boundary carries ``# pragma: no cover`` because the default
    test suite never performs a real HTTP request (AGENTS.md §6.2); the scrape
    flow is exercised through an injected fake fetcher instead. Non-success
    statuses and transport errors are normalized to
    :class:`~atlas.scrape.errors.FetchError`.

    A plain ``GET`` by default; pass ``method="POST"`` with a ``json_body`` for an
    ATS API that requires it (Workday). ``headers`` are merged on top of the
    default ``User-Agent``.

    Raises:
        FetchError: On a transport error or a non-success HTTP status.
    """
    merged_headers = {"User-Agent": _USER_AGENT, **(headers or {})}
    try:
        response = httpx.request(
            method,
            url,
            follow_redirects=True,
            timeout=timeout_s,
            headers=merged_headers,
            json=json_body,
        )
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise FetchError(f"Could not fetch {url}: {exc}") from exc
    return FetchResult(
        url=str(response.url),
        status_code=response.status_code,
        content_type=response.headers.get("content-type"),
        body=response.text,
    )
