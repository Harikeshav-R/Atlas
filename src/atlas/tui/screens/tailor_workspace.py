"""The Tailor workspace screen (PROJECT.md §8, screen #4).

Shows an application's source material and prepared materials side by side — the
master-resume blocks, the latest tailored selections (with each item's reason), and
a summary of the rendered resume / cover letter — and runs the four actions that
produce them.

Those actions call **synchronous, blocking** Atlas services: the AI provider chain
runs a subprocess (Claude Code) or a network request (OpenRouter), and rendering
runs WeasyPrint. Running them on Textual's event loop would freeze the UI, so each
is dispatched to a **thread worker** (``@work(thread=True)``) and its completion is
handled in :meth:`TailorWorkspaceScreen.on_worker_state_changed` — the first worker
in the codebase (§8: long-running actions never block the UI).

``exit_on_error=False`` keeps a failing service (a `TailoringError`, `RenderError`,
…) from tearing down the app: the error surfaces as a toast instead. When the app
was launched without an AI provider/renderer (``atlas tui`` builds them
best-effort), the AI/render actions are disabled and report a hint instead.

Editing the selections (include/exclude/pin) and per-section regenerate are the
deferred tailoring-depth follow-up (PROJECT.md §5.7, §5.8); this screen views and
runs.
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

from atlas.tui.data import build_tailor_workspace

if TYPE_CHECKING:
    from textual.worker import Worker

    from atlas.tui.app import AtlasApp
    from atlas.tui.data import TailorWorkspaceView

__all__ = ["TailorWorkspaceScreen"]

_DISABLED_HINT = "AI actions unavailable — check your backend with `atlas doctor`."


class TailorWorkspaceScreen(Screen[None]):
    """Master resume + tailored selections + materials, with the tailoring actions."""

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("t", "tailor", "Tailor"),
        Binding("c", "cover_letter", "Cover letter"),
        Binding("r", "rerender", "Re-render"),
        Binding("o", "open_materials", "Open"),
        Binding("escape", "app.pop_screen", "Back"),
    ]

    def __init__(self, application_id: int) -> None:
        """Remember which application the workspace is for."""
        super().__init__()
        self._application_id = application_id
        self._job_posting_id: int | None = None

    def compose(self) -> ComposeResult:
        """Lay out the header, summary, and the two content panes."""
        yield Header()
        with VerticalScroll(id="workspace"):
            yield Label(id="workspace-header")
            yield Label(id="workspace-summary")
            yield Label(id="workspace-status")
            yield Label("Tailored selections", classes="section-heading")
            yield DataTable(id="selections", cursor_type="none")
            yield Label("Master resume", classes="section-heading")
            yield DataTable(id="master-blocks", cursor_type="none")
        yield Footer()

    def on_mount(self) -> None:
        """Load and render the workspace."""
        self._populate(self._load())

    def _load(self) -> TailorWorkspaceView:
        app = cast("AtlasApp", self.app)
        return app.read(lambda session: build_tailor_workspace(session, self._application_id))

    def _populate(self, view: TailorWorkspaceView) -> None:
        """Fill the widgets from a freshly-loaded view model."""
        self._job_posting_id = view.job_posting_id
        self.query_one("#workspace-header", Label).update(
            f"#{view.application_id}  {view.title} @ {view.company}"
        )
        resume = "none" if view.resume_version is None else f"v{view.resume_version}"
        cover = "none" if view.cover_version is None else f"v{view.cover_version}"
        self.query_one("#workspace-summary", Label).update(
            f"Resume: {resume} ({view.resume_path or '—'})\n"
            f"Cover letter: {cover} ({view.cover_path or '—'})"
        )

        selections = self.query_one("#selections", DataTable)
        selections.clear(columns=True)
        selections.add_columns("Content id", "In", "Text", "Reason")
        for item in view.selections:
            selections.add_row(
                item.content_id,
                "yes" if item.included else "no",
                item.final_text,
                item.reason,
            )

        blocks = self.query_one("#master-blocks", DataTable)
        blocks.clear(columns=True)
        blocks.add_columns("Content id", "Type", "Text")
        for block in view.master_blocks:
            blocks.add_row(block.content_id, block.type, block.text)

    def _note(self, message: str) -> None:
        """Show a transient status line above the panes."""
        self.query_one("#workspace-status", Label).update(message)

    # --- actions ------------------------------------------------------------------

    def action_tailor(self) -> None:
        """Tailor the resume to the posting (AI + render), off the event loop."""
        if not self._require_actions():
            return
        assert self._job_posting_id is not None  # set when the view loaded
        self._note("Tailoring…")
        self._tailor_worker(self._job_posting_id)

    def action_cover_letter(self) -> None:
        """Write a cover letter for the posting (AI + render), off the event loop."""
        if not self._require_actions():
            return
        assert self._job_posting_id is not None  # set when the view loaded
        self._note("Writing the cover letter…")
        self._cover_worker(self._job_posting_id)

    def action_rerender(self) -> None:
        """Re-render the stored materials to fresh PDFs (no AI), off the event loop."""
        if not self._require_actions():
            return
        self._note("Re-rendering…")
        self._rerender_worker(self._application_id)

    def action_open_materials(self) -> None:
        """Open the rendered PDFs in the OS viewer, off the event loop."""
        self._note("Opening…")
        self._open_worker(self._application_id)

    def _require_actions(self) -> bool:
        """Return whether AI/render actions can run, noting a hint when they can't."""
        if cast("AtlasApp", self.app).actions_enabled:
            return True
        self._note(_DISABLED_HINT)
        self.notify(_DISABLED_HINT, severity="warning")
        return False

    # --- workers ------------------------------------------------------------------
    #
    # Each wraps one blocking service call. ``exclusive=True`` keeps a second press
    # from starting an overlapping run; ``exit_on_error=False`` routes failures to
    # on_worker_state_changed instead of tearing down the app.

    @work(thread=True, exclusive=True, exit_on_error=False, group="tailor")
    def _tailor_worker(self, posting_id: int) -> str:
        """Run the tailoring service and describe the result."""
        outcome = cast("AtlasApp", self.app).run_tailor(posting_id)
        return f"Tailored v{outcome.version} → {outcome.path} ({outcome.page_count}p)"

    @work(thread=True, exclusive=True, exit_on_error=False, group="tailor")
    def _cover_worker(self, posting_id: int) -> str:
        """Run the cover-letter service and describe the result."""
        outcome = cast("AtlasApp", self.app).run_cover_letter(posting_id)
        return f"Cover letter v{outcome.version} → {outcome.path}"

    @work(thread=True, exclusive=True, exit_on_error=False, group="tailor")
    def _rerender_worker(self, application_id: int) -> str:
        """Re-render the stored materials and describe the result."""
        outcome = cast("AtlasApp", self.app).run_rerender(application_id)
        resume = outcome.resume_path or "—"
        cover = outcome.cover_letter_path or "—"
        return f"Re-rendered: resume {resume}, cover {cover}"

    @work(thread=True, exclusive=True, exit_on_error=False, group="tailor")
    def _open_worker(self, application_id: int) -> str:
        """Open the rendered PDFs and describe what was opened."""
        outcome = cast("AtlasApp", self.app).run_open(application_id)
        return f"Opened {len(outcome.opened)} file(s)"

    def on_worker_state_changed(self, event: Worker.StateChanged) -> None:
        """Refresh + toast when a worker finishes, or report its error.

        Workers post their state changes back to the event loop, so this runs on the
        UI thread and may safely touch widgets.
        """
        if event.state is WorkerState.SUCCESS:
            message = str(event.worker.result)
            self._note(message)
            self._populate(self._load())
            self.notify(message)
        elif event.state is WorkerState.ERROR:
            message = str(event.worker.error)
            self._note(message)
            self.notify(message, severity="error")
