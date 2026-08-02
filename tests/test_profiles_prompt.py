"""Tests for the prompt boundary in :mod:`atlas.profiles.prompt`.

Only the non-I/O surface is exercised here — constructing :class:`RichPrompter`
and its console selection. The two ``ask_*`` methods read from the interactive
terminal, so they carry a justified ``# pragma: no cover`` and are driven in the
wizard tests through the scripted ``FakePrompter`` instead (AGENTS.md §6.2).
"""

from __future__ import annotations

from rich.console import Console

from atlas.cli.console import console as shared_console
from atlas.profiles.prompt import RichPrompter


def test_rich_prompter_defaults_to_shared_console() -> None:
    assert RichPrompter()._console is shared_console


def test_rich_prompter_accepts_an_injected_console() -> None:
    custom = Console()
    assert RichPrompter(custom)._console is custom
