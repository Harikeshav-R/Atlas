"""Error hierarchy for the Atlas render package."""

from __future__ import annotations

__all__ = [
    "NoMasterResumeError",
    "RenderError",
    "ThemeNotFoundError",
]


class RenderError(Exception):
    """Base class for every error raised by :mod:`atlas.render`."""


class NoMasterResumeError(RenderError):
    """Raised when a render is requested before a master resume has been set.

    Rendering turns the stored master resume into a PDF (PROJECT.md §5.11), so
    there is nothing to render until one is ingested. Carries a secret-free,
    human-readable message for the CLI to surface.
    """

    def __init__(self) -> None:
        """Build a human-readable message pointing at resume setup."""
        super().__init__("No master resume set — run `atlas resume set <path>` first.")


class ThemeNotFoundError(RenderError):
    """Raised when a configured theme has no template on disk.

    Carries the missing theme name so the CLI can render a specific, secret-free
    message.
    """

    def __init__(self, theme: str) -> None:
        """Store the missing theme name and build a human-readable message."""
        self.theme = theme
        super().__init__(f"No render theme named {theme!r}.")
