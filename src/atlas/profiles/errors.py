"""Error hierarchy for the Atlas profiles package."""

from __future__ import annotations

__all__ = ["ProfileNotFoundError", "ProfilesError"]


class ProfilesError(Exception):
    """Base class for every error raised by :mod:`atlas.profiles`."""


class ProfileNotFoundError(ProfilesError):
    """Raised when a profile is looked up by an id that does not exist.

    Carries the missing :attr:`profile_id` so callers (e.g. the CLI) can render a
    specific, secret-free message.
    """

    def __init__(self, profile_id: int) -> None:
        """Store the missing profile id and build a human-readable message."""
        self.profile_id = profile_id
        super().__init__(f"No profile with id {profile_id}.")
