"""Error hierarchy for the Atlas matching package."""

from __future__ import annotations

__all__ = [
    "MatchingError",
    "NoActiveProfileError",
    "NoMasterResumeError",
    "ScoringError",
]


class MatchingError(Exception):
    """Base class for every error raised by :mod:`atlas.matching`."""


class NoActiveProfileError(MatchingError):
    """Raised when scoring is requested but no profile is active.

    Scoring is always against a profile's preferences (PROJECT.md §5.6), so with
    no active profile there is nothing to score against. Carries a secret-free,
    human-readable message for the CLI to surface.
    """

    def __init__(self) -> None:
        """Build a human-readable message pointing at profile setup."""
        super().__init__("No active profile — run `atlas init` or `atlas profile use <id>`.")


class NoMasterResumeError(MatchingError):
    """Raised when scoring is requested before a master resume has been set.

    The fit assessment needs a compact summary of the master resume (PROJECT.md
    §5.6, §7), so scoring cannot proceed until one is ingested.
    """

    def __init__(self) -> None:
        """Build a human-readable message pointing at resume setup."""
        super().__init__("No master resume set — run `atlas resume set <path>` first.")


class ScoringError(MatchingError):
    """Raised when the AI backend never produces a usable fit assessment.

    Unlike the scrape parser (which degrades to keeping the raw page text), a
    bogus score would pollute the ranked queue, so a failed scoring call surfaces
    as an error rather than a placeholder row.
    """
