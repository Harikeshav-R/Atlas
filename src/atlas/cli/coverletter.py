"""Cover-letter-outcome display for the Atlas CLI.

The ``atlas cover`` command (PROJECT.md §9, §5.8) keeps its Typer wiring thin in
:mod:`atlas.cli.main` and delegates the display here, mirroring the ``atlas
tailor`` split (:mod:`atlas.cli.tailor`): this module holds the **pure, I/O-light**
rendering of a :class:`~atlas.coverletter.service.CoverLetterOutcome` through the
shared semantic theme, so it is testable without invoking the CLI (AGENTS.md §6.2).
The generation orchestration itself lives in
:func:`atlas.coverletter.service.write_application_cover_letter`; machine-readable
``--json`` output is produced directly from the outcome's
:meth:`~pydantic.BaseModel.model_dump_json`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from rich.console import Group
from rich.table import Table
from rich.text import Text

if TYPE_CHECKING:
    from rich.console import RenderableType

    from atlas.coverletter.service import CoverLetterOutcome

__all__ = ["render_cover_letter_outcome"]

#: How each grounding source reads in the display.
_GROUNDED_LABELS = {
    "tailored_resume": "tailored resume",
    "master_resume": "master resume",
}


def render_cover_letter_outcome(outcome: CoverLetterOutcome) -> RenderableType:
    """Render a :class:`~atlas.coverletter.service.CoverLetterOutcome` as a renderable.

    Produces a header (title @ company), a grid of the PDF path, application id,
    version, tone, grounding source, and page count (``warning``-styled when the
    letter did not fit one page), and a muted list of the gaps.
    """
    header = Text.assemble(
        (outcome.title, "heading"),
        ("  ", ""),
        (f"@ {outcome.company}", "accent"),
    )

    grid = Table.grid(padding=(0, 2))
    grid.add_column(style="muted", no_wrap=True)
    grid.add_column()
    grid.add_row("Cover letter", Text(outcome.path, style="accent"))
    grid.add_row("Application", str(outcome.application_id))
    grid.add_row("Version", f"v{outcome.version}")
    grid.add_row("Tone", outcome.tone)
    grid.add_row("Grounded on", _GROUNDED_LABELS.get(outcome.grounded_on, outcome.grounded_on))

    parts: list[RenderableType] = [header, Text(), grid]
    if outcome.one_page:
        grid.add_row("Pages", Text(str(outcome.page_count), style="ok"))
    else:
        grid.add_row("Pages", Text(str(outcome.page_count), style="warning"))
        parts.extend(
            [
                Text(),
                Text(
                    f"⚠ {outcome.page_count} pages — the letter is long; consider trimming.",
                    style="warning",
                ),
            ]
        )
    parts.extend([Text(), _gaps_line(outcome.gaps)])
    return Group(*parts)


def _gaps_line(gaps: list[str]) -> RenderableType:
    """Render the unsupported-keyword gaps, or a muted 'none' when empty."""
    if not gaps:
        return Text.assemble(("Gaps: ", "muted"), ("none", "muted"))
    return Text.assemble(("Gaps: ", "muted"), (", ".join(gaps), "warning"))
