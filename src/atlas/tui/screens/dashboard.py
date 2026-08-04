"""The Dashboard screen (PROJECT.md §8).

Shows the pipeline funnel, the active profile, recent activity, and upcoming
deadlines. All data comes from the pure :func:`atlas.tui.data.build_dashboard_report`
builder; this screen only lays it out.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.screen import Screen
from textual.widgets import DataTable, Footer, Header, Label

from atlas.tui.data import build_dashboard_report

if TYPE_CHECKING:
    from atlas.tui.app import AtlasApp

__all__ = ["DashboardScreen"]


class DashboardScreen(Screen[None]):
    """Pipeline funnel + active profile + recent activity + deadlines."""

    def compose(self) -> ComposeResult:
        """Lay out the dashboard sections."""
        yield Header()
        with VerticalScroll(id="dashboard"):
            yield Label(id="profile")
            yield Label("Pipeline", classes="section-heading")
            yield DataTable(id="funnel", cursor_type="none")
            yield Label("Recent activity", classes="section-heading")
            yield DataTable(id="recent", cursor_type="row")
            yield Label("Upcoming deadlines", classes="section-heading")
            yield DataTable(id="deadlines", cursor_type="none")
        yield Footer()

    def on_mount(self) -> None:
        """Load the report and populate the tables."""
        app = cast("AtlasApp", self.app)
        report = app.read(build_dashboard_report)

        profile = report.active_profile or "none"
        self.query_one("#profile", Label).update(
            f"Active profile: {profile}    Applications: {report.total_applications}"
        )

        funnel = self.query_one("#funnel", DataTable)
        funnel.add_columns("Stage", "Count")
        for bar in report.funnel:
            funnel.add_row(bar.status, str(bar.count))

        recent = self.query_one("#recent", DataTable)
        recent.add_columns("ID", "Status", "Title", "Company", "Updated")
        for item in report.recent:
            recent.add_row(
                str(item.id),
                item.status,
                item.title,
                item.company,
                item.updated_at.date().isoformat(),
            )

        deadlines = self.query_one("#deadlines", DataTable)
        deadlines.add_columns("Due", "Title", "Company", "Status")
        for entry in report.deadlines:
            deadlines.add_row(
                entry.due.date().isoformat(),
                entry.title,
                entry.company,
                entry.status,
            )
