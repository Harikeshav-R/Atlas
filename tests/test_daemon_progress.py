"""Tests for the daemon's progress-reporting seam in :mod:`atlas.daemon.progress`."""

from __future__ import annotations

from atlas.daemon.progress import ProgressUpdate, emit_progress


def test_emit_progress_none_callback_is_a_noop() -> None:
    # A None sink is the default; emitting must simply do nothing (no raise).
    emit_progress(None, ProgressUpdate(stage="start"))


def test_emit_progress_forwards_the_update() -> None:
    seen: list[ProgressUpdate] = []
    update = ProgressUpdate(stage="item", label="greenhouse:acme", done=1, total=3)
    emit_progress(seen.append, update)
    assert seen == [update]


def test_emit_progress_swallows_a_raising_callback() -> None:
    # A UI progress sink that raises must never propagate out of the poll.
    def boom(_: ProgressUpdate) -> None:
        raise RuntimeError("sink failed")

    emit_progress(boom, ProgressUpdate(stage="done", done=3, total=3))


def test_progress_update_defaults() -> None:
    update = ProgressUpdate(stage="start")
    assert update.label == ""
    assert update.done == 0
    assert update.total is None
