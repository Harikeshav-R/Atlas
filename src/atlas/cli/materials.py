"""Re-render / open outcome display for the Atlas CLI.

The ``atlas render`` and ``atlas open`` commands (PROJECT.md §9) keep their Typer
wiring thin in :mod:`atlas.cli.main` and delegate the display here, mirroring the
other CLI render splits: this module holds the **pure, I/O-light** rendering of the
:class:`~atlas.materials.service.RerenderOutcome` / :class:`~atlas.materials.service.OpenOutcome`
through the shared semantic theme, so it is testable without invoking the CLI
(AGENTS.md §6.2). The orchestration lives in :mod:`atlas.materials.service`;
``--json`` output is produced directly from each outcome's
:meth:`~pydantic.BaseModel.model_dump_json`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from rich.console import Group
from rich.table import Table
from rich.text import Text

if TYPE_CHECKING:
    from rich.console import RenderableType

    from atlas.materials.service import OpenOutcome, RerenderOutcome

__all__ = ["render_open_outcome", "render_rerender_outcome"]


def render_rerender_outcome(outcome: RerenderOutcome) -> RenderableType:
    """Render a :class:`~atlas.materials.service.RerenderOutcome` as a renderable.

    Shows the re-rendered resume and cover-letter PDF paths, with a muted ``"—"``
    for any material the application does not have yet.
    """
    header = Text.assemble(
        ("Re-rendered application ", "heading"), (str(outcome.application_id), "accent")
    )
    grid = Table.grid(padding=(0, 2))
    grid.add_column(style="muted", no_wrap=True)
    grid.add_column()
    grid.add_row("Resume", _path_text(outcome.resume_path))
    grid.add_row("Cover letter", _path_text(outcome.cover_letter_path))
    return Group(header, Text(), grid)


def render_open_outcome(outcome: OpenOutcome) -> RenderableType:
    """Render an :class:`~atlas.materials.service.OpenOutcome` as a renderable.

    Lists the PDF paths that were opened, or a muted note when there was nothing
    to open.
    """
    if not outcome.opened:
        return Text(
            f"Nothing to open for application {outcome.application_id} — "
            "run `atlas tailor` or `atlas cover` first.",
            style="muted",
        )
    header = Text.assemble(
        ("Opened for application ", "heading"), (str(outcome.application_id), "accent")
    )
    lines = [Text.assemble(("- ", "muted"), (path, "accent")) for path in outcome.opened]
    return Group(header, Text(), *lines)


def _path_text(path: str | None) -> Text:
    """Render a PDF path, or a muted ``"—"`` when the material is absent."""
    if path is None:
        return Text("—", style="muted")
    return Text(path, style="accent")
