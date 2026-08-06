"""Daemon status rendering for the Atlas CLI.

The ``atlas daemon`` commands (PROJECT.md §9) keep their Typer wiring thin in
:mod:`atlas.cli.main` and delegate the display here, mirroring the other CLI
render modules: this holds the **pure, I/O-light** rendering of a
:class:`~atlas.daemon.service.DaemonStatus` through the shared semantic theme, so
it is testable without invoking the CLI (AGENTS.md §6.2). The lifecycle logic
itself lives in :mod:`atlas.daemon.service`; ``--json`` output comes straight from
the status model's :meth:`~pydantic.BaseModel.model_dump_json`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from rich.table import Table
from rich.text import Text

if TYPE_CHECKING:
    from rich.console import RenderableType

    from atlas.daemon.ipc import ProgressEvent, ResultEvent
    from atlas.daemon.service import DaemonStatus

__all__ = ["render_daemon_status", "render_poll_progress", "render_poll_result"]


def render_daemon_status(status: DaemonStatus) -> RenderableType:
    """Render a :class:`~atlas.daemon.service.DaemonStatus` as a styled Rich grid."""
    grid = Table.grid(padding=(0, 2))
    grid.add_column(style="muted", no_wrap=True)
    grid.add_column()
    if status.running:
        grid.add_row("Daemon", Text("running", style="success"))
        grid.add_row("PID", str(status.pid))
    else:
        grid.add_row("Daemon", Text("stopped", style="muted"))
    return grid


def render_poll_progress(event: ProgressEvent) -> Text:
    """Render one streamed poll :class:`~atlas.daemon.ipc.ProgressEvent` as a line.

    A ``start`` shows the phase and its known total; an ``item`` shows the running
    ``done``/``total`` count and the unit label; a ``done`` closes the phase.
    """
    if event.stage == "start":
        total = "" if event.total is None else f" (0/{event.total})"
        return Text.assemble((f"{event.phase}", "accent"), (f": starting{total}", "muted"))
    if event.stage == "item":
        total = "?" if event.total is None else str(event.total)
        return Text.assemble(
            (f"{event.phase}", "accent"),
            (f": {event.done}/{total} {event.label}", "muted"),
        )
    return Text.assemble((f"{event.phase}", "accent"), (": done", "muted"))


def render_poll_result(result: ResultEvent) -> RenderableType:
    """Render a poll's terminal :class:`~atlas.daemon.ipc.ResultEvent` as a grid."""
    grid = Table.grid(padding=(0, 2))
    grid.add_column(style="muted", no_wrap=True)
    grid.add_column()
    grid.add_row("Discovered", Text(str(result.discovered), style="success"))
    grid.add_row("Scored", Text(str(result.scored), style="success"))
    grid.add_row("Skipped", str(result.skipped))
    failed_style = "error" if result.failed_sources else "muted"
    grid.add_row("Failed sources", Text(str(result.failed_sources), style=failed_style))
    if result.inactive:
        grid.add_row(
            "Needs API key",
            Text(f"{result.inactive} (run atlas source key)", style="warning"),
        )
    if result.claimed:
        grid.add_row("Claimed by another worker", str(result.claimed))
    return grid
