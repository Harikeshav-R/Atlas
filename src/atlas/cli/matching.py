"""Fit-score rendering for the Atlas CLI.

The ``atlas score`` command (PROJECT.md §9) keeps its Typer wiring thin in
:mod:`atlas.cli.main` and delegates the display here, mirroring the ``atlas
postings`` split (:mod:`atlas.cli.scrape`): this module holds the **pure,
I/O-light** rendering of a :class:`~atlas.matching.service.ScoreOutcome` through
the shared semantic theme, so it is testable without invoking the CLI (AGENTS.md
§6.2). The scoring orchestration itself lives in
:func:`atlas.matching.service.score_posting`, which the command calls within one
:func:`~atlas.db.session.session_scope` transaction; machine-readable ``--json``
output is produced directly from the outcome's
:meth:`~pydantic.BaseModel.model_dump_json`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from rich.console import Group
from rich.table import Table
from rich.text import Text

from atlas.matching.structure import SignalStatus, Verdict

if TYPE_CHECKING:
    from rich.console import RenderableType

    from atlas.matching.service import ScoreOutcome

__all__ = ["render_score", "verdict_style"]

#: Semantic theme style for each verdict, so a strong fit reads green and a weak
#: one reads red across every command that shows a verdict.
_VERDICT_STYLES: dict[str, str] = {
    Verdict.STRONG.value: "success",
    Verdict.GOOD.value: "ok",
    Verdict.STRETCH.value: "warning",
    Verdict.WEAK.value: "bad",
}

#: Semantic theme style for each deterministic-signal status.
_SIGNAL_STYLES: dict[str, str] = {
    SignalStatus.MATCH.value: "ok",
    SignalStatus.MISMATCH.value: "bad",
    SignalStatus.UNKNOWN.value: "muted",
}


def verdict_style(verdict: str) -> str:
    """Return the semantic theme style name for ``verdict`` (``muted`` if unknown)."""
    return _VERDICT_STYLES.get(verdict, "muted")


def render_score(outcome: ScoreOutcome) -> RenderableType:
    """Render a :class:`~atlas.matching.service.ScoreOutcome` as a Rich renderable.

    Produces a header (title @ company), a grid of the score / verdict / salary
    fit / deterministic-signal badges, the rationale, and the matched strengths /
    gaps / dealbreaker-hit lists, all through the shared semantic theme. Empty
    lists render as a muted ``"—"``.
    """
    header = Text.assemble(
        (outcome.title, "heading"),
        ("  ", ""),
        (f"@ {outcome.company}", "accent"),
    )

    grid = Table.grid(padding=(0, 2))
    grid.add_column(style="muted", no_wrap=True)
    grid.add_column()
    grid.add_row("Posting", str(outcome.posting_id))
    grid.add_row("Score", Text(f"{outcome.score}/100", style="accent"))
    grid.add_row("Verdict", Text(outcome.verdict, style=verdict_style(outcome.verdict)))
    grid.add_row("Salary fit", outcome.salary_fit)

    signals = outcome.signals
    grid.add_row("Salary signal", _signal_text(signals.salary.value))
    grid.add_row("Location", _signal_text(signals.location.value))
    grid.add_row("Work auth", _signal_text(signals.work_auth.value))
    grid.add_row("Deal-breakers", _list_text(signals.dealbreakers))

    return Group(
        header,
        Text(),
        grid,
        Text(),
        Text(outcome.rationale or "—"),
        Text(),
        _section("Matched strengths", outcome.matched_strengths, empty_style="muted"),
        _section("Gaps", outcome.gaps, empty_style="muted"),
        _section("Dealbreaker hits", outcome.dealbreaker_hits, empty_style="muted"),
    )


def _signal_text(status: str) -> Text:
    """Render a deterministic-signal status through its semantic style."""
    return Text(status, style=_SIGNAL_STYLES.get(status, "muted"))


def _list_text(items: list[str]) -> Text:
    """Render a list of strings as a comma-joined muted line, or ``"—"`` when empty."""
    return Text(", ".join(items) or "—", style="muted")


def _section(heading: str, items: list[str], *, empty_style: str) -> RenderableType:
    """Render a titled bullet list, or a muted ``"—"`` placeholder when empty."""
    if not items:
        return Text.assemble((f"{heading}: ", "muted"), ("—", empty_style))
    table = Table.grid(padding=(0, 1))
    table.add_column()
    table.add_row(Text(f"{heading}:", style="heading"))
    for item in items:
        table.add_row(Text(f"- {item}"))
    return table
