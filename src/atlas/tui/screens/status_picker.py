"""A modal that picks a target status for an application (PROJECT.md §5.12, §8).

Returned to the caller via ``push_screen(..., callback)``: the dismissed value is
the chosen :class:`~atlas.tracking.status.ApplicationStatus`, or ``None`` if the
user cancelled. The caller applies the transition (validated by the state machine)
and shows the result.
"""

from __future__ import annotations

from typing import ClassVar

from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Label, OptionList
from textual.widgets.option_list import Option

from atlas.tracking.status import ApplicationStatus

__all__ = ["StatusPickerScreen"]


class StatusPickerScreen(ModalScreen[ApplicationStatus | None]):
    """Pick a target status from the full set of pipeline stages."""

    BINDINGS: ClassVar[list[BindingType]] = [Binding("escape", "cancel", "Cancel")]

    def compose(self) -> ComposeResult:
        """Lay out the status option list."""
        with Vertical(id="status-picker"):
            yield Label("Move to status", classes="section-heading")
            yield OptionList(
                *(Option(status.value, id=status.value) for status in ApplicationStatus)
            )

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        """Dismiss with the chosen status."""
        assert event.option.id is not None  # every option carries a status id
        self.dismiss(ApplicationStatus(event.option.id))

    def action_cancel(self) -> None:
        """Dismiss without choosing a status."""
        self.dismiss(None)
