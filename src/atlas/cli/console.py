"""Shared Rich console and theme for the Atlas CLI.

Every command renders through the single :data:`console` defined here, styled by
one :data:`ATLAS_THEME`, so output is *pretty and consistent* across the whole
application (AGENTS.md §10) — never ad-hoc ``print``/``typer.echo`` of plain
strings. Commands reference **semantic** style names (``success``, ``error``,
``heading``, …) rather than hard-coding colors, so the palette can evolve in one
place and every command follows.

The one exception is machine-readable output (e.g. ``atlas doctor --json``),
which must stay unstyled so it can be piped and parsed; emit that via
:func:`print_json_line`.
"""

from __future__ import annotations

from rich.console import Console
from rich.theme import Theme

__all__ = ["ATLAS_THEME", "console", "error_console", "print_json_line"]

# Semantic styles — commands use these names, not raw colors, for consistency.
ATLAS_THEME = Theme(
    {
        "success": "bold green",
        "warning": "bold yellow",
        "error": "bold red",
        "heading": "bold cyan",
        "muted": "dim",
        "accent": "cyan",
        # Status marks used across commands (e.g. availability rows).
        "ok": "bold green",
        "bad": "bold red",
    }
)

#: The shared console for normal (stdout) output. All human-facing rendering goes
#: through this instance so theming and width handling are uniform.
console = Console(theme=ATLAS_THEME)

#: Console for diagnostics/errors, routed to stderr so it never contaminates
#: stdout that a caller may be capturing (e.g. piped ``--json``).
error_console = Console(theme=ATLAS_THEME, stderr=True)


def print_json_line(payload: str) -> None:
    """Print pre-serialized JSON to stdout verbatim, without Rich styling.

    Machine-readable output must not carry ANSI styling or Rich's own JSON
    reflow, so this writes the string exactly (``soft_wrap`` + no highlighting)
    for reliable piping and parsing.
    """
    console.print(payload, soft_wrap=True, highlight=False, markup=False)
