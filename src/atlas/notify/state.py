"""Persistence for the daemon's desktop-notification run-state (PROJECT.md §5.16).

The daemon must not re-notify about the same match or deadline every poll, so it
records a small run-state between ticks: the high-water mark of the last match
score it alerted on, the running per-day notification count (for the daily cap),
and the deadline keys already alerted. This lives as a single JSON file under the
platformdirs **state dir**.

Read/write mirror the config-loader and probe-cache idiom
(:mod:`atlas.ai.probe_cache`): writes create the parent directory and dump
``model_dump(mode="json")``, reads guard on existence, and a missing *or*
unreadable/corrupt file is treated as **fresh default state** rather than an error
— so a hand-mangled or partially-written state file can never crash the daemon
(the worst case is one duplicate notification).
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from pydantic import BaseModel, Field, ValidationError

from atlas.config.paths import notify_state_file

__all__ = ["NotifyState", "load_notify_state", "save_notify_state"]

logger = logging.getLogger(__name__)


class NotifyState(BaseModel):
    """The daemon's persisted desktop-notification run-state.

    Attributes:
        last_notified_score_id: The greatest :class:`~atlas.db.models.MatchScore`
            ``id`` already notified about; the next poll only alerts on higher ids
            (append-only, monotonic), so a re-poll never re-notifies a match.
        day: The calendar day (``"YYYY-MM-DD"``) the :attr:`daily_count` counts;
            when the daemon sees a new day it resets the count.
        daily_count: How many notifications have been posted on :attr:`day` so far,
            enforced against the config's daily cap.
        notified_deadline_keys: Stable per-deadline keys already alerted (a
            deadline has no monotonic id), so an approaching deadline is announced
            once.
    """

    last_notified_score_id: int = 0
    day: str = ""
    daily_count: int = 0
    notified_deadline_keys: list[str] = Field(default_factory=list)


def load_notify_state(path: Path | None = None) -> NotifyState:
    """Load the notification run-state, or a fresh default when unavailable.

    A missing file, unreadable bytes, invalid JSON, or a payload that no longer
    matches :class:`NotifyState` all yield a fresh default state (the daemon just
    starts from scratch — at worst one duplicate notification), never an exception.

    Args:
        path: The state file to read; defaults to
            :func:`~atlas.config.paths.notify_state_file`.

    Returns:
        The persisted :class:`NotifyState`, or a default when the file is absent
        or unusable.
    """
    target = path if path is not None else notify_state_file()
    if not target.exists():
        return NotifyState()
    try:
        return NotifyState.model_validate_json(target.read_text(encoding="utf-8"))
    except (OSError, ValueError, ValidationError):
        # Corrupt/mangled state — start fresh so the daemon never crashes on it.
        # Logged (without the contents) so a persistently unreadable file is
        # diagnosable rather than silently ignored.
        logger.warning("Ignoring unreadable notification state; starting fresh.")
        return NotifyState()


def save_notify_state(state: NotifyState, path: Path | None = None) -> None:
    """Write ``state`` to the state file as JSON.

    Creates the state directory if needed (:func:`~atlas.config.paths.state_dir`
    does not), matching the config/probe-cache writer idiom.

    Args:
        state: The run-state to persist.
        path: The destination file; defaults to
            :func:`~atlas.config.paths.notify_state_file`.
    """
    target = path if path is not None else notify_state_file()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(state.model_dump(mode="json"), indent=2), encoding="utf-8")
