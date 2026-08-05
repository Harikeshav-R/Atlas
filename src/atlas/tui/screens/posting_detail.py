"""The Posting-detail screen (PROJECT.md §8, screen #3).

Shows one posting's normalized fields and its latest fit, and can **tailor** the
posting (AI + render) — the §8 screen-#3 action. Data comes from the existing
:func:`atlas.cli.scrape.build_posting_detail` builder; the Tailor action runs off
the event loop via a thread worker (the :mod:`atlas.tui.screens.tailor_workspace`
pattern) and, on success, navigates to the new application's detail screen.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar, cast

from textual import work
from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import VerticalScroll
from textual.screen import Screen
from textual.widgets import Footer, Header, Label
from textual.worker import WorkerState

from atlas.cli.scrape import build_posting_detail
from atlas.tui.screens.application_detail import ApplicationDetailScreen

if TYPE_CHECKING:
    from textual.worker import Worker

    from atlas.tailor.service import TailorOutcome
    from atlas.tui.app import AtlasApp

__all__ = ["PostingDetailScreen"]

_DISABLED_HINT = "AI actions unavailable — check your backend with `atlas doctor`."


class PostingDetailScreen(Screen[None]):
    """A posting's normalized fields + latest fit, with the Tailor action."""

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("t", "tailor", "Tailor"),
        Binding("escape", "app.pop_screen", "Back"),
    ]

    def __init__(self, posting_id: int) -> None:
        """Remember which posting to show."""
        super().__init__()
        self._posting_id = posting_id

    def compose(self) -> ComposeResult:
        """Lay out the header, field grid, and description."""
        yield Header()
        with VerticalScroll(id="posting"):
            yield Label(id="posting-header")
            yield Label(id="posting-fields")
            yield Label("Description", classes="section-heading")
            yield Label(id="posting-description")
        yield Footer()

    def on_mount(self) -> None:
        """Load and render the posting detail."""
        app = cast("AtlasApp", self.app)
        detail = app.read(lambda session: build_posting_detail(session, self._posting_id))

        self.query_one("#posting-header", Label).update(f"{detail.title} @ {detail.company}")
        fit = "unscored" if detail.score is None else f"{detail.score} {detail.verdict}"
        self.query_one("#posting-fields", Label).update(
            f"Location: {detail.location or '—'}    Remote: {detail.remote_type or '—'}    "
            f"Seniority: {detail.seniority or '—'}    Fit: {fit}\n"
            f"Keywords: {', '.join(detail.keywords) or '—'}\n"
            f"Apply: {detail.apply_url}"
        )
        self.query_one("#posting-description", Label).update(detail.description or "—")

    def action_tailor(self) -> None:
        """Tailor this posting (AI + render), off the event loop."""
        if not cast("AtlasApp", self.app).actions_enabled:
            self.notify(_DISABLED_HINT, severity="warning")
            return
        self.notify("Tailoring…")
        self._tailor_worker(self._posting_id)

    @work(thread=True, exclusive=True, exit_on_error=False, group="tailor")
    def _tailor_worker(self, posting_id: int) -> TailorOutcome:
        """Run the tailoring service off the event loop and return its outcome."""
        return cast("AtlasApp", self.app).run_tailor(posting_id)

    def on_worker_state_changed(self, event: Worker.StateChanged) -> None:
        """Navigate to the new application on success, or toast the error."""
        if event.state is WorkerState.SUCCESS:
            outcome = cast("TailorOutcome", event.worker.result)
            self.notify(f"Tailored → application {outcome.application_id}.")
            self.app.push_screen(ApplicationDetailScreen(outcome.application_id))
        elif event.state is WorkerState.ERROR:
            self.notify(str(event.worker.error), severity="error")
