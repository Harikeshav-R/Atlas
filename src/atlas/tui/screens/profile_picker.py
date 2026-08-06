"""A modal that picks a profile to make active (PROJECT.md §5.2, §8).

Mirrors :class:`~atlas.tui.screens.status_picker.StatusPickerScreen`: returned to
the caller via ``push_screen(..., callback)``, the dismissed value is the chosen
profile's id, or ``None`` if the user cancelled. The caller (the Discover screen)
switches the active profile and re-ranks its queue to that profile's scores.

The list of profiles comes from the pure
:func:`atlas.tui.data.build_profile_choices` builder, so the screen stays a thin
presentation layer (the choices are testable without Textual).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Label, OptionList
from textual.widgets.option_list import Option

if TYPE_CHECKING:
    from atlas.tui.data import ProfileChoices

__all__ = ["ProfilePickerScreen"]


class ProfilePickerScreen(ModalScreen[int | None]):
    """Pick a profile to activate from the list of profiles."""

    BINDINGS: ClassVar[list[BindingType]] = [Binding("escape", "cancel", "Cancel")]

    def __init__(self, choices: ProfileChoices) -> None:
        """Store the profiles to offer (built by ``build_profile_choices``)."""
        super().__init__()
        self._choices = choices

    def compose(self) -> ComposeResult:
        """Lay out the profile option list (the active one marked)."""
        with Vertical(id="profile-picker"):
            yield Label("Switch profile", classes="section-heading")
            yield OptionList(
                *(
                    Option(f"{'● ' if choice.active else '  '}{choice.name}", id=str(choice.id))
                    for choice in self._choices.choices
                )
            )

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        """Dismiss with the chosen profile's id."""
        assert event.option.id is not None  # every option carries a profile id
        self.dismiss(int(event.option.id))

    def action_cancel(self) -> None:
        """Dismiss without choosing a profile."""
        self.dismiss(None)
