"""The Atlas TUI screens (PROJECT.md §8).

Each screen is a thin Textual presentation layer over a pure view-model builder
(:mod:`atlas.tui.data`) or a reused CLI builder; none holds data logic.
"""

from __future__ import annotations

from atlas.tui.screens.application_detail import ApplicationDetailScreen
from atlas.tui.screens.applications import ApplicationsScreen
from atlas.tui.screens.dashboard import DashboardScreen
from atlas.tui.screens.posting_detail import PostingDetailScreen
from atlas.tui.screens.status_picker import StatusPickerScreen

__all__ = [
    "ApplicationDetailScreen",
    "ApplicationsScreen",
    "DashboardScreen",
    "PostingDetailScreen",
    "StatusPickerScreen",
]
