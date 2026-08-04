"""The Applications screen (PROJECT.md §8).

Lists tracked applications in a table (default) or a Kanban board grouped by
status; the user can drill into an application's detail or change its stage. Data
comes from :func:`atlas.cli.tracking.build_applications_report`; status changes go
through :meth:`atlas.tui.app.AtlasApp.change_status`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar, cast

from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Horizontal, VerticalScroll
from textual.screen import Screen
from textual.widgets import DataTable, Footer, Header, Label, ListItem, ListView

from atlas.cli.tracking import build_applications_report
from atlas.tracking.errors import InvalidStatusTransitionError
from atlas.tracking.status import ApplicationStatus
from atlas.tui.screens.application_detail import ApplicationDetailScreen
from atlas.tui.screens.status_picker import StatusPickerScreen

if TYPE_CHECKING:
    from atlas.cli.tracking import ApplicationListReport
    from atlas.tui.app import AtlasApp

__all__ = ["ApplicationsScreen"]


class ApplicationsScreen(Screen[None]):
    """Table + Kanban views of the tracked applications."""

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("k", "toggle_view", "Table/Kanban"),
        Binding("s", "set_status", "Set status"),
    ]

    def __init__(self) -> None:
        """Start in the table view."""
        super().__init__()
        self._kanban = False

    def compose(self) -> ComposeResult:
        """Lay out both views (only one is shown at a time)."""
        yield Header()
        yield DataTable(id="apps-table", cursor_type="row")
        yield Horizontal(id="apps-kanban")
        yield Footer()

    def on_mount(self) -> None:
        """Load the applications, render the active view, and focus the table."""
        self._refresh()
        self.query_one("#apps-table", DataTable).focus()

    def _report(self) -> ApplicationListReport:
        app = cast("AtlasApp", self.app)
        return app.read(build_applications_report)

    def _refresh(self) -> None:
        """Rebuild both views from the latest data and show the active one."""
        report = self._report()

        table = self.query_one("#apps-table", DataTable)
        table.clear(columns=True)
        table.add_columns("ID", "Status", "Title", "Company", "Fit", "Applied")
        for row in report.applications:
            fit = "—" if row.score is None else f"{row.score} {row.verdict}"
            applied = "—" if row.applied_at is None else row.applied_at.date().isoformat()
            table.add_row(str(row.id), row.status, row.title, row.company, fit, applied)

        kanban = self.query_one("#apps-kanban", Horizontal)
        kanban.remove_children()
        for status in ApplicationStatus:
            column = [row for row in report.applications if row.status == status.value]
            items = [ListItem(Label(f"#{row.id} {row.title}")) for row in column]
            kanban.mount(
                VerticalScroll(
                    Label(f"{status.value} ({len(column)})", classes="section-heading"),
                    ListView(*items),
                    classes="kanban-column",
                )
            )

        self._apply_view()

    def _apply_view(self) -> None:
        """Show the table or the Kanban board per the current toggle."""
        self.query_one("#apps-table", DataTable).display = not self._kanban
        self.query_one("#apps-kanban", Horizontal).display = self._kanban

    def action_toggle_view(self) -> None:
        """Flip between the table and Kanban views."""
        self._kanban = not self._kanban
        self._apply_view()

    def _selected_application_id(self) -> int | None:
        """Return the id of the highlighted table row, or ``None`` if empty."""
        table = self.query_one("#apps-table", DataTable)
        if table.row_count == 0:
            return None
        row = table.get_row_at(table.cursor_row)
        return int(row[0])

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        """Open the Application-detail screen for the selected row (Enter/click)."""
        application_id = int(event.data_table.get_row(event.row_key)[0])
        self.app.push_screen(ApplicationDetailScreen(application_id))

    def action_set_status(self) -> None:
        """Open the status picker for the highlighted application."""
        application_id = self._selected_application_id()
        if application_id is None:
            return

        def apply(target: ApplicationStatus | None) -> None:
            if target is not None:
                self._change_status(application_id, target)

        self.app.push_screen(StatusPickerScreen(), apply)

    def _change_status(self, application_id: int, target: ApplicationStatus) -> None:
        """Apply a status change, refresh, and toast the result."""
        app = cast("AtlasApp", self.app)
        try:
            outcome = app.change_status(application_id, target)
        except InvalidStatusTransitionError as exc:
            self.notify(str(exc), severity="error")
            return
        self._refresh()
        self.notify(f"{outcome.previous_status} → {outcome.new_status}")
