"""Error hierarchy for the Atlas tailoring package."""

from __future__ import annotations

__all__ = [
    "NoActiveProfileError",
    "NoMasterResumeError",
    "TailoringError",
    "TailoringOutputError",
]


class TailoringError(Exception):
    """Base class for every error raised by :mod:`atlas.tailor`."""


class NoActiveProfileError(TailoringError):
    """Raised when tailoring is requested but no profile is active.

    Tailoring foregrounds the active profile's emphasis (PROJECT.md §5.7), so with
    no active profile there is nothing to tailor toward. Carries a secret-free,
    human-readable message for the CLI to surface.
    """

    def __init__(self) -> None:
        """Build a human-readable message pointing at profile setup."""
        super().__init__("No active profile — run `atlas init` or `atlas profile use <id>`.")


class NoMasterResumeError(TailoringError):
    """Raised when tailoring is requested before a master resume has been set.

    Tailoring selects and rewords content from the master resume (PROJECT.md
    §5.7), so it cannot proceed until one is ingested.
    """

    def __init__(self) -> None:
        """Build a human-readable message pointing at resume setup."""
        super().__init__("No master resume set — run `atlas resume set <path>` first.")


class TailoringOutputError(TailoringError):
    """Raised when the AI backend never produces a usable tailored resume.

    Like fit scoring, a bogus tailored resume would mislead the user, so a failed
    tailoring call surfaces as an error rather than degrading to a placeholder.
    """
