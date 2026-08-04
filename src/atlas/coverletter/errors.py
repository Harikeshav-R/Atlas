"""Error hierarchy for the Atlas cover-letter package."""

from __future__ import annotations

__all__ = [
    "CoverLetterError",
    "CoverLetterOutputError",
    "NoActiveProfileError",
    "NoMasterResumeError",
]


class CoverLetterError(Exception):
    """Base class for every error raised by :mod:`atlas.coverletter`."""


class NoActiveProfileError(CoverLetterError):
    """Raised when a cover letter is requested but no profile is active.

    The letter is written for the active profile's job hunt (PROJECT.md §5.8), so
    with no active profile there is nothing to write toward. Carries a secret-free,
    human-readable message for the CLI to surface.
    """

    def __init__(self) -> None:
        """Build a human-readable message pointing at profile setup."""
        super().__init__("No active profile — run `atlas init` or `atlas profile use <id>`.")


class NoMasterResumeError(CoverLetterError):
    """Raised when a cover letter is requested with no material to ground it.

    The letter is grounded in the tailored resume's selections or, failing that,
    the master resume (PROJECT.md §5.8); with neither there is nothing truthful to
    write from.
    """

    def __init__(self) -> None:
        """Build a human-readable message pointing at resume setup."""
        super().__init__("No master resume set — run `atlas resume set <path>` first.")


class CoverLetterOutputError(CoverLetterError):
    """Raised when the AI backend never produces a usable cover letter.

    Like tailoring, a bogus letter would mislead the user, so a failed generation
    surfaces as an error rather than degrading to a placeholder.
    """
