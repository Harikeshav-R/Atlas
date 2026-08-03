"""Error hierarchy for the Atlas resume package."""

from __future__ import annotations

__all__ = ["MasterResumeNotFoundError", "ResumeError", "ResumeSourceError"]


class ResumeError(Exception):
    """Base class for every error raised by :mod:`atlas.resume`."""


class MasterResumeNotFoundError(ResumeError):
    """Raised when an operation needs a master resume but none exists yet.

    Raised by :func:`atlas.resume.service.apply_reparse` (and the repository's
    version lookup) so the CLI can point the user at ``atlas resume set <path>``.
    """


class ResumeSourceError(ResumeError):
    """Raised when the master-resume source file cannot be read.

    Covers a missing path, a directory in place of a file, or an unreadable file.
    Carries a secret-free, human-readable message for the CLI to surface.
    """
