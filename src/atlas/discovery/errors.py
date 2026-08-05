"""Error hierarchy for the Atlas discovery package.

Mirrors :mod:`atlas.daemon.errors` / :mod:`atlas.scrape.errors`: a package base
error plus specific errors carrying a clear, secret-free message for the CLI (and
the discovery poll) to surface. A failing ATS source raises a :class:`DiscoveryError`
(or the reused :class:`~atlas.scrape.errors.FetchError`) that the best-effort poll
catches per source, so one bad board never aborts the whole poll.
"""

from __future__ import annotations

from collections.abc import Iterable

__all__ = [
    "DiscoveryError",
    "UnknownAggregatorError",
    "UnknownAtsError",
]


class DiscoveryError(Exception):
    """Base class for every error raised by :mod:`atlas.discovery`.

    Also raised directly by an ATS adapter whose board response is unusable (a
    non-JSON body, or a payload missing the expected ``jobs`` array), so the poll
    can skip that source best-effort.
    """


class UnknownAtsError(DiscoveryError):
    """Raised when an ATS provider name has no registered adapter.

    Carries the unknown :attr:`ats_type` and the list of :attr:`supported`
    providers so the CLI can render a specific, secret-free message.
    """

    def __init__(self, ats_type: str, supported: Iterable[str]) -> None:
        """Store the unknown provider and build a human-readable message."""
        self.ats_type = ats_type
        self.supported = tuple(supported)
        supported_list = ", ".join(self.supported) if self.supported else "none"
        super().__init__(f"Unknown ATS provider {ats_type!r}. Supported: {supported_list}.")


class UnknownAggregatorError(DiscoveryError):
    """Raised when an aggregator name has no registered adapter.

    Carries the unknown :attr:`aggregator` and the list of :attr:`supported`
    providers so the CLI can render a specific, secret-free message (mirroring
    :class:`UnknownAtsError`).
    """

    def __init__(self, aggregator: str, supported: Iterable[str]) -> None:
        """Store the unknown provider and build a human-readable message."""
        self.aggregator = aggregator
        self.supported = tuple(supported)
        supported_list = ", ".join(self.supported) if self.supported else "none"
        super().__init__(f"Unknown aggregator {aggregator!r}. Supported: {supported_list}.")
