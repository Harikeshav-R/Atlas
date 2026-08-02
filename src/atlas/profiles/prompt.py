"""The interactive prompt boundary for the onboarding wizard.

The wizard (:mod:`atlas.profiles.onboarding`) never talks to the terminal
directly: it asks questions through a :class:`Prompter`, a tiny protocol with two
primitives — free-text and yes/no. Everything else (splitting comma-separated
lists, parsing optional integers, mapping tokens to enums, re-prompting on
invalid input) is **pure wizard logic** over those primitives, so the whole flow
is driven by a scripted fake in the hermetic suite with no TTY (AGENTS.md §6.2),
exactly like the injectable handler factory in :mod:`atlas.logging`.

:class:`RichPrompter` is the real implementation. Its two methods are thin
wrappers over :mod:`rich.prompt` on the shared console, so they are the only
lines that read from the interactive terminal — and thus the only ones carrying a
justified ``# pragma: no cover`` (the same treatment
:func:`atlas.logging._default_handler_factory` gets for opening the real
console/log file).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from rich.prompt import Confirm, Prompt

from atlas.cli.console import console as _shared_console

if TYPE_CHECKING:
    from rich.console import Console

__all__ = ["Prompter", "RichPrompter"]


class Prompter(Protocol):
    """A minimal question-asking boundary the wizard drives (injectable seam)."""

    def ask_text(self, message: str, *, default: str = "") -> str:
        """Ask a free-text question, returning the (possibly empty) answer.

        A non-empty ``default`` is offered as the pre-filled value (used in edit
        mode); an empty ``default`` marks the field skippable.
        """

    def ask_bool(self, message: str, *, default: bool) -> bool:
        """Ask a yes/no question, returning the answer (``default`` on empty)."""


class RichPrompter:
    """A :class:`Prompter` backed by :mod:`rich.prompt` on the shared console.

    Rendered through the shared Atlas console so onboarding matches the rest of
    the CLI (AGENTS.md §10). The two methods are the sole interactive-I/O surface,
    so each is pragma'd rather than exercised in the hermetic suite.
    """

    def __init__(self, console: Console | None = None) -> None:
        """Store the console to prompt on (defaults to the shared Atlas console)."""
        self._console = console if console is not None else _shared_console

    def ask_text(  # pragma: no cover - reads from the interactive console (AGENTS.md §6.2)
        self, message: str, *, default: str = ""
    ) -> str:
        """Prompt for free text on the shared console."""
        return Prompt.ask(
            message, console=self._console, default=default, show_default=bool(default)
        )

    def ask_bool(  # pragma: no cover - reads from the interactive console (AGENTS.md §6.2)
        self, message: str, *, default: bool
    ) -> bool:
        """Prompt for a yes/no answer on the shared console."""
        return Confirm.ask(message, console=self._console, default=default)
