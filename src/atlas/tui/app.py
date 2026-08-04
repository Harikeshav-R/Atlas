"""The Atlas Textual application (PROJECT.md §8).

:class:`AtlasApp` is the interactive TUI. It owns a database engine (injected, so
tests drive it with the in-memory ``db_engine`` fixture) and opens a short
:func:`~atlas.db.session.session_scope` per read or status change. The screens
(:mod:`atlas.tui.screens`) are a thin presentation layer over the pure view-model
builders in :mod:`atlas.tui.data` and the existing CLI builders — all data logic
stays out of the widgets so it is covered without a running terminal.

The blocking launcher (`atlas tui`) lives in :mod:`atlas.cli.main`; only the real
:meth:`textual.app.App.run` call there carries ``# pragma: no cover``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar, TypeVar

from textual.app import App
from textual.binding import Binding, BindingType

from atlas.db import session_scope
from atlas.tracking.service import StatusChangeOutcome, set_application_status
from atlas.tui.screens.applications import ApplicationsScreen
from atlas.tui.screens.dashboard import DashboardScreen

if TYPE_CHECKING:
    from collections.abc import Callable

    from sqlalchemy.engine import Engine
    from sqlmodel import Session

    from atlas.tracking.status import ApplicationStatus

__all__ = ["AtlasApp"]

_T = TypeVar("_T")


class AtlasApp(App[None]):
    """The Atlas job-application co-pilot TUI."""

    TITLE = "Atlas"
    CSS_PATH = "app.tcss"

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("d", "dashboard", "Dashboard"),
        Binding("a", "applications", "Applications"),
        Binding("q", "quit", "Quit"),
    ]

    def __init__(self, *, engine: Engine) -> None:
        """Store the database engine the screens read and write through."""
        super().__init__()
        self._engine = engine

    def on_mount(self) -> None:
        """Open on the Dashboard."""
        self.push_screen(DashboardScreen())

    def read(self, fn: Callable[[Session], _T]) -> _T:
        """Run a read ``fn`` inside a short transaction and return its result."""
        with session_scope(self._engine) as session:
            return fn(session)

    def change_status(self, application_id: int, target: ApplicationStatus) -> StatusChangeOutcome:
        """Move an application to ``target`` (validated by the state machine).

        Raises:
            ApplicationNotFoundError: If the application no longer exists.
            InvalidStatusTransitionError: If the move is not permitted.
        """
        with session_scope(self._engine) as session:
            return set_application_status(session, application_id, target)

    def action_dashboard(self) -> None:
        """Switch to the Dashboard screen."""
        self.switch_screen(DashboardScreen())

    def action_applications(self) -> None:
        """Switch to the Applications screen."""
        self.switch_screen(ApplicationsScreen())
