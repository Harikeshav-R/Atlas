"""The Discover screen (PROJECT.md §8, screen #2).

A ranked queue of **scored postings** — the piece that makes the daemon's
discovery/scoring work visible and actionable in the TUI (closing Journey B:
background discovery → review → tailor). A :class:`~textual.widgets.DataTable`
lists each posting's score / verdict / company / title / location / salary /
source / queue state (highest fit first), with the AI's rationale shown in a
detail pane below the table as the cursor moves.

Actions (§8): ``enter`` drills into :class:`~atlas.tui.screens.posting_detail.PostingDetailScreen`;
``t`` tailors the posting (AI + render, off the event loop via a thread worker —
the same pattern as :mod:`atlas.tui.screens.tailor_workspace`); ``x`` dismisses a
posting (hiding it from the queue); ``s`` saves it for later; ``o`` opens its apply
URL in the browser. Data comes from the pure
:func:`atlas.tui.data.build_discover_queue` builder.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar, cast

from textual import work
from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import VerticalScroll
from textual.screen import Screen
from textual.widgets import DataTable, Footer, Header, Label
from textual.worker import WorkerState

from atlas.matching.structure import QueueStatus
from atlas.platform.browser import UrlOpenError
from atlas.tui.data import build_discover_queue
from atlas.tui.screens.application_detail import ApplicationDetailScreen
from atlas.tui.screens.posting_detail import PostingDetailScreen

if TYPE_CHECKING:
    from textual.worker import Worker

    from atlas.tailor.service import TailorOutcome
    from atlas.tui.app import AtlasApp
    from atlas.tui.data import DiscoverQueue

__all__ = ["DiscoverScreen"]

_DISABLED_HINT = "AI actions unavailable — check your backend with `atlas doctor`."
_EMPTY_HINT = "No scored postings yet — add or discover some, then let scoring run."


class DiscoverScreen(Screen[None]):
    """Ranked queue of scored postings, with the review actions."""

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("t", "tailor", "Tailor"),
        Binding("x", "pass_posting", "Dismiss"),
        Binding("s", "save", "Save"),
        Binding("o", "open_url", "Open URL"),
        Binding("escape", "app.pop_screen", "Back"),
    ]

    def __init__(self) -> None:
        """Start with no loaded rows."""
        super().__init__()
        # Posting ids and rationales in row order, so a cursor row maps back to
        # its posting by index (the ranked queue never reorders within a render).
        self._posting_ids: list[int] = []
        self._rationales: list[str] = []

    def compose(self) -> ComposeResult:
        """Lay out the queue table and the rationale detail pane."""
        yield Header()
        with VerticalScroll(id="discover"):
            yield DataTable(id="discover-table", cursor_type="row")
            yield Label(id="discover-rationale")
        yield Footer()

    def on_mount(self) -> None:
        """Load the queue and focus the table."""
        self._refresh()
        self.query_one("#discover-table", DataTable).focus()

    def _queue(self) -> DiscoverQueue:
        return cast("AtlasApp", self.app).read(build_discover_queue)

    def _refresh(self) -> None:
        """Rebuild the table from the ranked queue."""
        queue = self._queue()
        table = self.query_one("#discover-table", DataTable)
        table.clear(columns=True)
        table.add_columns(
            "Score", "Verdict", "Company", "Title", "Location", "Salary", "Source", "Queue"
        )
        self._posting_ids = [row.id for row in queue.rows]
        self._rationales = [row.rationale for row in queue.rows]
        for row in queue.rows:
            table.add_row(
                str(row.score),
                row.verdict,
                row.company,
                row.title,
                row.location or "—",
                row.salary,
                row.source,
                row.queue_status,
            )
        rationale = queue.rows[0].rationale if queue.rows else _EMPTY_HINT
        self.query_one("#discover-rationale", Label).update(rationale)

    def _selected_posting_id(self) -> int | None:
        """Return the posting id for the highlighted row, or ``None`` if empty."""
        table = self.query_one("#discover-table", DataTable)
        if table.row_count == 0:
            return None
        return self._posting_ids[table.cursor_row]

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        """Show the highlighted posting's rationale in the detail pane."""
        self.query_one("#discover-rationale", Label).update(self._rationales[event.cursor_row])

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        """Drill into the highlighted posting's detail on Enter."""
        self.app.push_screen(PostingDetailScreen(self._posting_ids[event.cursor_row]))

    # --- actions ------------------------------------------------------------------

    def action_pass_posting(self) -> None:
        """Dismiss (hide) the highlighted posting from the queue."""
        self._set_status(QueueStatus.DISMISSED, "Dismissed")

    def action_save(self) -> None:
        """Flag the highlighted posting to revisit (it stays in the queue)."""
        self._set_status(QueueStatus.SAVED, "Saved")

    def _set_status(self, status: QueueStatus, verb: str) -> None:
        """Set the highlighted posting's queue status, then refresh + toast."""
        posting_id = self._selected_posting_id()
        if posting_id is None:
            return
        cast("AtlasApp", self.app).set_queue_status(posting_id, status)
        self._refresh()
        self.notify(f"{verb} posting {posting_id}.")

    def action_open_url(self) -> None:
        """Open the highlighted posting's apply URL in the browser."""
        posting_id = self._selected_posting_id()
        if posting_id is None:
            return
        try:
            url = cast("AtlasApp", self.app).run_open_url(posting_id)
        except UrlOpenError as exc:
            self.notify(str(exc), severity="error")
            return
        self.notify(f"Opened {url}")

    def action_tailor(self) -> None:
        """Tailor the highlighted posting (AI + render), off the event loop."""
        if not cast("AtlasApp", self.app).actions_enabled:
            self.notify(_DISABLED_HINT, severity="warning")
            return
        posting_id = self._selected_posting_id()
        if posting_id is None:
            return
        self.notify("Tailoring…")
        self._tailor_worker(posting_id)

    @work(thread=True, exclusive=True, exit_on_error=False, group="tailor")
    def _tailor_worker(self, posting_id: int) -> TailorOutcome:
        """Run the tailoring service off the event loop and return its outcome."""
        return cast("AtlasApp", self.app).run_tailor(posting_id)

    def on_worker_state_changed(self, event: Worker.StateChanged) -> None:
        """Navigate to the new application on success, or toast the error.

        Workers post state changes back to the event loop, so this runs on the UI
        thread and may safely push a screen / touch widgets.
        """
        if event.state is WorkerState.SUCCESS:
            outcome = cast("TailorOutcome", event.worker.result)
            self.notify(f"Tailored → application {outcome.application_id}.")
            self.app.push_screen(ApplicationDetailScreen(outcome.application_id))
        elif event.state is WorkerState.ERROR:
            self.notify(str(event.worker.error), severity="error")
