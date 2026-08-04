"""The Application-detail screen (PROJECT.md §8).

Shows one application's status timeline, prepared materials, fit, and notes, and
lets the user change its stage or open the underlying posting. Data comes from the
pure :func:`atlas.tui.data.build_application_detail` builder.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar, cast

from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import VerticalScroll
from textual.screen import Screen
from textual.widgets import DataTable, Footer, Header, Label

from atlas.tracking.errors import InvalidStatusTransitionError
from atlas.tui.data import build_application_detail
from atlas.tui.screens.status_picker import StatusPickerScreen

if TYPE_CHECKING:
    from atlas.tracking.status import ApplicationStatus
    from atlas.tui.app import AtlasApp
    from atlas.tui.data import ApplicationDetail

__all__ = ["ApplicationDetailScreen"]


class ApplicationDetailScreen(Screen[None]):
    """Status timeline + materials + fit for one application."""

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("s", "set_status", "Set status"),
        Binding("t", "tailor_workspace", "Tailor"),
        Binding("p", "open_posting", "Open posting"),
        Binding("escape", "app.pop_screen", "Back"),
    ]

    def __init__(self, application_id: int) -> None:
        """Remember which application to show."""
        super().__init__()
        self._application_id = application_id
        self._job_posting_id: int | None = None

    def compose(self) -> ComposeResult:
        """Lay out the header, summary, materials, and timeline."""
        yield Header()
        with VerticalScroll(id="detail"):
            yield Label(id="detail-header")
            yield Label(id="detail-summary")
            yield Label(id="detail-materials")
            yield Label("Status history", classes="section-heading")
            yield DataTable(id="timeline", cursor_type="none")
        yield Footer()

    def on_mount(self) -> None:
        """Load and render the application detail."""
        self._populate(self._load())

    def _load(self) -> ApplicationDetail:
        app = cast("AtlasApp", self.app)
        return app.read(lambda session: build_application_detail(session, self._application_id))

    def _populate(self, detail: ApplicationDetail) -> None:
        """Populate the widgets from a freshly-loaded detail model."""
        self.query_one("#detail-header", Label).update(
            f"#{detail.id}  {detail.title} @ {detail.company}"
        )
        fit = "unscored" if detail.score is None else f"{detail.score} {detail.verdict}"
        applied = "—" if detail.applied_at is None else detail.applied_at.date().isoformat()
        self.query_one("#detail-summary", Label).update(
            f"Status: {detail.status}    Fit: {fit}    "
            f"Applied: {applied}    Outcome: {detail.outcome or '—'}"
        )
        resume = "none" if detail.tailored_resume is None else f"v{detail.tailored_resume.version}"
        cover = "none" if detail.cover_letter is None else f"v{detail.cover_letter.version}"
        self.query_one("#detail-materials", Label).update(
            f"Resume: {resume}    Cover letter: {cover}"
        )

        timeline = self.query_one("#timeline", DataTable)
        timeline.clear(columns=True)
        timeline.add_columns("When", "From", "To", "Forced")
        for entry in detail.timeline:
            timeline.add_row(
                entry.at.date().isoformat(),
                entry.from_status,
                entry.to_status,
                "yes" if entry.forced else "",
            )

    def action_set_status(self) -> None:
        """Open the status picker and apply the chosen transition."""

        def apply(target: ApplicationStatus | None) -> None:
            if target is not None:
                self._change_status(target)

        self.app.push_screen(StatusPickerScreen(), apply)

    def _change_status(self, target: ApplicationStatus) -> None:
        """Apply a status change, re-render, and toast the result."""
        app = cast("AtlasApp", self.app)
        try:
            outcome = app.change_status(self._application_id, target)
        except InvalidStatusTransitionError as exc:
            self.notify(str(exc), severity="error")
            return
        self._populate(self._load())
        self.notify(f"{outcome.previous_status} → {outcome.new_status}")

    def action_tailor_workspace(self) -> None:
        """Open the Tailor workspace for this application."""
        from atlas.tui.screens.tailor_workspace import TailorWorkspaceScreen

        self.app.push_screen(TailorWorkspaceScreen(self._application_id))

    def action_open_posting(self) -> None:
        """Open the posting-detail screen for this application's posting."""
        app = cast("AtlasApp", self.app)
        from atlas.tailor.repository import get_application
        from atlas.tui.screens.posting_detail import PostingDetailScreen

        posting_id = app.read(
            lambda session: get_application(session, self._application_id).job_posting_id
        )
        self.app.push_screen(PostingDetailScreen(posting_id))
