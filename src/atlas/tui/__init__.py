"""The Atlas interactive Textual TUI (PROJECT.md §8).

The core screens — Dashboard, Applications (table + Kanban), Application detail,
and Posting detail — presented over the data the Phase 1 CLI features persist.
:class:`~atlas.tui.app.AtlasApp` is the application; the ``atlas tui`` command in
:mod:`atlas.cli.main` launches it. All data logic lives in the pure builders of
:mod:`atlas.tui.data` (and the reused CLI builders), so the screens stay a thin,
testable presentation layer driven by Textual's ``Pilot`` harness.
"""

from __future__ import annotations

from atlas.tui.app import AtlasApp

__all__ = ["AtlasApp"]
