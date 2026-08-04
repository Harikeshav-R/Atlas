"""The Posting-detail screen (PROJECT.md §8).

Shows one posting's normalized fields and its latest fit. Data comes from the
existing :func:`atlas.cli.scrape.build_posting_detail` builder.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar, cast

from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import VerticalScroll
from textual.screen import Screen
from textual.widgets import Footer, Header, Label

from atlas.cli.scrape import build_posting_detail

if TYPE_CHECKING:
    from atlas.tui.app import AtlasApp

__all__ = ["PostingDetailScreen"]


class PostingDetailScreen(Screen[None]):
    """A posting's normalized fields + latest fit."""

    BINDINGS: ClassVar[list[BindingType]] = [Binding("escape", "app.pop_screen", "Back")]

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
