"""Error hierarchy for the Atlas AI-prompt template library."""

from __future__ import annotations

__all__ = ["PromptError", "PromptNotFoundError"]


class PromptError(Exception):
    """Base class for every error raised by :mod:`atlas.ai.prompts`."""


class PromptNotFoundError(PromptError):
    """Raised when a task/version has no matching prompt template.

    Signals a programming error (a task or version that was never authored),
    carrying a message that names the missing task and version.
    """
