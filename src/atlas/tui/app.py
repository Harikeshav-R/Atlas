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

from atlas.coverletter.service import write_application_cover_letter
from atlas.db import session_scope
from atlas.materials.service import open_application, rerender_application
from atlas.platform.browser import default_url_opener
from atlas.platform.opener import default_file_opener
from atlas.scrape.repository import get_posting, set_posting_queue_status
from atlas.tailor.service import tailor_posting
from atlas.tracking.service import StatusChangeOutcome, set_application_status
from atlas.tui.screens.applications import ApplicationsScreen
from atlas.tui.screens.dashboard import DashboardScreen
from atlas.tui.screens.discover import DiscoverScreen

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from sqlalchemy.engine import Engine
    from sqlmodel import Session

    from atlas.ai.base import LLMProvider
    from atlas.config.schema import RenderConfig, TailoringConfig
    from atlas.coverletter.service import CoverLetterOutcome
    from atlas.db.models import JobPosting
    from atlas.matching.structure import QueueStatus
    from atlas.materials.service import OpenOutcome, RerenderOutcome
    from atlas.platform.browser import UrlOpener
    from atlas.platform.opener import FileOpener
    from atlas.render.renderer import PdfRenderer
    from atlas.tailor.service import TailorOutcome
    from atlas.tracking.status import ApplicationStatus

__all__ = ["AtlasApp"]

_T = TypeVar("_T")


class AtlasApp(App[None]):
    """The Atlas job-application co-pilot TUI."""

    TITLE = "Atlas"
    CSS_PATH = "app.tcss"

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("d", "dashboard", "Dashboard"),
        Binding("w", "discover", "Discover"),
        Binding("a", "applications", "Applications"),
        Binding("q", "quit", "Quit"),
    ]

    def __init__(
        self,
        *,
        engine: Engine,
        provider: LLMProvider | None = None,
        renderer: PdfRenderer | None = None,
        opener: FileOpener = default_file_opener,
        url_opener: UrlOpener = default_url_opener,
        tailoring: TailoringConfig | None = None,
        render_config: RenderConfig | None = None,
        renders_dir: Path | None = None,
    ) -> None:
        """Store the engine and the (optional) action boundaries.

        The read/track screens need only ``engine``. The Tailor workspace's
        AI/render actions additionally need ``provider`` + ``renderer`` +
        ``tailoring`` + ``render_config``; when any is absent the app runs
        **browse-only** and those actions are disabled (see :attr:`actions_enabled`).
        The ``opener`` (PDFs) and ``url_opener`` (apply URLs) are always available
        (opening needs no AI).
        """
        super().__init__()
        self._engine = engine
        self._provider = provider
        self._renderer = renderer
        self._opener = opener
        self._url_opener = url_opener
        self._tailoring = tailoring
        self._render_config = render_config
        self._renders_dir = renders_dir

    @property
    def actions_enabled(self) -> bool:
        """Whether the Tailor workspace's AI/render actions can run.

        ``True`` only when the AI provider, the PDF renderer, and both config
        blocks were built and injected (the ``atlas tui`` launcher does this
        best-effort; a missing key or bad config leaves the app browse-only).
        """
        return (
            self._provider is not None
            and self._renderer is not None
            and self._tailoring is not None
            and self._render_config is not None
        )

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

    def set_queue_status(self, posting_id: int, status: QueueStatus) -> JobPosting:
        """Set a posting's Discover-queue triage state (dismiss / save).

        Raises:
            JobPostingNotFoundError: If the posting no longer exists.
        """
        with session_scope(self._engine) as session:
            return set_posting_queue_status(session, posting_id, status)

    def run_open_url(self, posting_id: int) -> str:
        """Open a posting's apply URL in the browser and return the URL.

        Raises:
            JobPostingNotFoundError: If the posting no longer exists.
            UrlOpenError: If no browser could be launched.
        """
        with session_scope(self._engine) as session:
            url = get_posting(session, posting_id).apply_url
        self._url_opener(url)
        return url

    # --- blocking service calls (run inside a Textual thread worker) --------------
    #
    # Each opens its own short transaction and calls a synchronous Atlas service
    # that blocks — the AI provider chain (subprocess or network) and WeasyPrint
    # rendering — so the Tailor workspace dispatches them off the event loop
    # (PROJECT.md §8). The boundaries come from the injected provider/renderer/
    # config, mirroring how the CLI builds them per command. Each asserts the
    # action-capable invariant the caller checks via :attr:`actions_enabled`.

    def run_tailor(self, posting_id: int) -> TailorOutcome:
        """Tailor the resume for ``posting_id`` (AI + render); blocking."""
        assert self._provider is not None
        assert self._renderer is not None
        assert self._tailoring is not None
        assert self._render_config is not None
        with session_scope(self._engine) as session:
            return tailor_posting(
                session,
                posting_id,
                provider=self._provider,
                renderer=self._renderer,
                honesty_level=self._tailoring.honesty_level.value,
                theme=self._render_config.resume_theme,
                enforce_one_page=self._tailoring.enforce_one_page,
                renders_dir=self._renders_dir,
            )

    def run_cover_letter(self, posting_id: int) -> CoverLetterOutcome:
        """Write a cover letter for ``posting_id`` (AI + render); blocking."""
        assert self._provider is not None
        assert self._renderer is not None
        assert self._tailoring is not None
        assert self._render_config is not None
        with session_scope(self._engine) as session:
            return write_application_cover_letter(
                session,
                posting_id,
                provider=self._provider,
                renderer=self._renderer,
                honesty_level=self._tailoring.honesty_level.value,
                theme=self._render_config.cover_theme,
                renders_dir=self._renders_dir,
            )

    def run_rerender(self, application_id: int) -> RerenderOutcome:
        """Re-render an application's materials from stored content (no AI); blocking."""
        assert self._renderer is not None
        assert self._render_config is not None
        with session_scope(self._engine) as session:
            return rerender_application(
                session,
                application_id,
                renderer=self._renderer,
                resume_theme=self._render_config.resume_theme,
                cover_theme=self._render_config.cover_theme,
                renders_dir=self._renders_dir,
            )

    def run_open(self, application_id: int) -> OpenOutcome:
        """Open an application's rendered PDFs in the OS viewer; blocking."""
        with session_scope(self._engine) as session:
            return open_application(session, application_id, opener=self._opener)

    def action_dashboard(self) -> None:
        """Switch to the Dashboard screen."""
        self.switch_screen(DashboardScreen())

    def action_discover(self) -> None:
        """Switch to the Discover screen (the ranked scored-posting queue)."""
        self.switch_screen(DiscoverScreen())

    def action_applications(self) -> None:
        """Switch to the Applications screen."""
        self.switch_screen(ApplicationsScreen())
