"""Render-outcome display for the Atlas CLI.

The ``atlas resume render`` command (PROJECT.md §9, §5.11) keeps its Typer wiring
thin in :mod:`atlas.cli.main` and delegates the display here, mirroring the
``atlas score`` split (:mod:`atlas.cli.matching`): this module holds the **pure,
I/O-light** rendering of a :class:`~atlas.render.service.RenderOutcome` through the
shared semantic theme, so it is testable without invoking the CLI (AGENTS.md §6.2).
The render orchestration itself lives in
:func:`atlas.render.service.render_master_resume`; machine-readable ``--json``
output is produced directly from the outcome's
:meth:`~pydantic.BaseModel.model_dump_json`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from rich.console import Group
from rich.table import Table
from rich.text import Text

if TYPE_CHECKING:
    from rich.console import RenderableType

    from atlas.render.service import RenderOutcome

__all__ = ["render_render_outcome"]


def render_render_outcome(outcome: RenderOutcome) -> RenderableType:
    """Render a :class:`~atlas.render.service.RenderOutcome` as a Rich renderable.

    Produces a header plus a grid of the output path, page count, resume version,
    and theme, and — when the render exceeded one page — a ``warning``-styled note
    that one-page enforcement (a later tailoring step) will trim it.
    """
    header = Text("Rendered resume", style="heading")

    grid = Table.grid(padding=(0, 2))
    grid.add_column(style="muted", no_wrap=True)
    grid.add_column()
    grid.add_row("Path", Text(outcome.path, style="accent"))
    grid.add_row("Version", f"v{outcome.version}")
    grid.add_row("Theme", outcome.theme)
    if outcome.one_page:
        grid.add_row("Pages", Text(str(outcome.page_count), style="ok"))
        return Group(header, Text(), grid)

    grid.add_row("Pages", Text(str(outcome.page_count), style="warning"))
    note = Text(
        f"⚠ {outcome.page_count} pages — exceeds one page; tailoring will trim it to fit.",
        style="warning",
    )
    return Group(header, Text(), grid, Text(), note)
