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

    from atlas.daemon.service import DaemonStatus

__all__ = ["render_daemon_status"]


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
