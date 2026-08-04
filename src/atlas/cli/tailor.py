"""Tailor-outcome display for the Atlas CLI.

The ``atlas tailor`` command (PROJECT.md §9, §5.7) keeps its Typer wiring thin in
:mod:`atlas.cli.main` and delegates the display here, mirroring the ``atlas resume
render`` split (:mod:`atlas.cli.render`): this module holds the **pure, I/O-light**
rendering of a :class:`~atlas.tailor.service.TailorOutcome` through the shared
semantic theme, so it is testable without invoking the CLI (AGENTS.md §6.2). The
tailoring orchestration itself lives in
:func:`atlas.tailor.service.tailor_posting`; machine-readable ``--json`` output is
produced directly from the outcome's :meth:`~pydantic.BaseModel.model_dump_json`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from rich.console import Group
from rich.table import Table
from rich.text import Text

if TYPE_CHECKING:
    from rich.console import RenderableType

    from atlas.tailor.service import TailorOutcome

__all__ = ["render_tailor_outcome"]


def render_tailor_outcome(outcome: TailorOutcome) -> RenderableType:
    """Render a :class:`~atlas.tailor.service.TailorOutcome` as a Rich renderable.

    Produces a header (title @ company), a grid of the PDF path, application id,
    version, included-block count, and page count (with a ``warning``-styled page
    count when the resume did not fit one page), and a muted list of the gaps —
    posting keywords that could not be truthfully supported.
    """
    header = Text.assemble(
        (outcome.title, "heading"),
        ("  ", ""),
        (f"@ {outcome.company}", "accent"),
    )

    grid = Table.grid(padding=(0, 2))
    grid.add_column(style="muted", no_wrap=True)
    grid.add_column()
    grid.add_row("Tailored PDF", Text(outcome.path, style="accent"))
    grid.add_row("Application", str(outcome.application_id))
    grid.add_row("Version", f"v{outcome.version}")
    grid.add_row("Included blocks", str(outcome.included_count))
    if outcome.one_page:
        grid.add_row("Pages", Text(str(outcome.page_count), style="ok"))
        page_note: RenderableType | None = None
    else:
        grid.add_row("Pages", Text(str(outcome.page_count), style="warning"))
        page_note = Text(
            f"⚠ {outcome.page_count} pages — could not trim to one page; "
            "edit the master resume or lower content.",
            style="warning",
        )

    gaps_line = _gaps_line(outcome.gaps)
    parts: list[RenderableType] = [header, Text(), grid]
    if page_note is not None:
        parts.extend([Text(), page_note])
    parts.extend([Text(), gaps_line])
    return Group(*parts)


def _gaps_line(gaps: list[str]) -> RenderableType:
    """Render the unsupported-keyword gaps, or a muted 'none' when empty."""
    if not gaps:
        return Text.assemble(("Gaps: ", "muted"), ("none", "muted"))
    return Text.assemble(("Gaps: ", "muted"), (", ".join(gaps), "warning"))
