"""Error hierarchy for the Atlas scrape package."""

from __future__ import annotations

__all__ = [
    "ExtractionError",
    "FetchError",
    "JobPostingNotFoundError",
    "ScrapeError",
]


class ScrapeError(Exception):
    """Base class for every error raised by :mod:`atlas.scrape`."""


class FetchError(ScrapeError):
    """Raised when a posting URL cannot be fetched.

    Covers a network failure, a non-success HTTP status, or a non-HTML response.
    Carries a secret-free, human-readable message for the CLI to surface.
    """


class ExtractionError(ScrapeError):
    """Raised when a fetched page yields no usable job-posting content.

    Raised only when neither the deterministic extractors nor the AI pass could
    produce a posting with at least a title — the page had nothing to work with.
    """


class JobPostingNotFoundError(ScrapeError):
    """Raised when a job posting is looked up by an id that does not exist.

    Carries the missing :attr:`posting_id` so the CLI can render a specific,
    secret-free message.
    """

    def __init__(self, posting_id: int) -> None:
        """Store the missing posting id and build a human-readable message."""
        self.posting_id = posting_id
        super().__init__(f"No job posting with id {posting_id}.")
