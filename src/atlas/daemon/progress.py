"""A tiny progress-reporting seam for the daemon's polls (PROJECT.md §4.1).

The daemon's IPC surface streams a poll's progress to the TUI/CLI as it runs, so
each poll needs a way to report per-source / per-pair progress without knowing
anything about transports. This module defines the boundary — a small
:class:`ProgressUpdate` model and a :data:`ProgressCallback` alias — plus the
:func:`emit_progress` helper that reports an update **best-effort**: a callback
that raises must never break the poll (a UI sink dying is not a poll failure).

Both the scoring poll (:mod:`atlas.daemon.poll`) and the discovery/aggregator
polls (:mod:`atlas.discovery.poller`) import from here rather than from each
other, so there is no edge between those two poll modules.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Literal

from pydantic import BaseModel

__all__ = ["ProgressCallback", "ProgressUpdate", "emit_progress"]

_LOGGER = logging.getLogger(__name__)


class ProgressUpdate(BaseModel):
    """One progress step reported by a poll.

    Attributes:
        stage: ``"start"`` before the work begins, ``"item"`` after each unit
            (a source or a ``(posting, profile)`` pair) is processed, and
            ``"done"`` once the poll finishes.
        label: A short human-readable label for the unit just processed (e.g.
            ``"greenhouse:acme"`` or ``"Backend Engineer x posting 12"``); empty
            for the ``start`` / ``done`` brackets.
        done: How many units have been processed so far (``0`` at ``start``).
        total: The total number of units when known up front (the source count),
            or ``None`` when it cannot be known in advance (the scoring poll's
            nested profile x posting loops).
    """

    stage: Literal["start", "item", "done"]
    label: str = ""
    done: int = 0
    total: int | None = None


#: A sink a poll pushes :class:`ProgressUpdate`s to (injected; ``None`` = silent).
ProgressCallback = Callable[[ProgressUpdate], None]


def emit_progress(callback: ProgressCallback | None, update: ProgressUpdate) -> None:
    """Report ``update`` to ``callback`` if one was given, best-effort.

    A ``None`` callback is a no-op (the poll runs without a progress sink). A
    callback that raises is logged and swallowed, never propagated — progress
    reporting is advisory and must never abort or corrupt the poll.
    """
    if callback is None:
        return
    try:
        callback(update)
    except Exception:
        # A UI progress sink dying is not a poll failure — log and carry on.
        _LOGGER.debug("Progress callback raised; ignoring.", exc_info=True)
