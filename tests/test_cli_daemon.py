"""Tests for the daemon-status rendering in :mod:`atlas.cli.daemon`."""

from __future__ import annotations

from rich.console import RenderableType

from atlas.cli.console import console
from atlas.cli.daemon import render_daemon_status, render_poll_progress, render_poll_result
from atlas.daemon.ipc import ProgressEvent, ResultEvent
from atlas.daemon.service import DaemonStatus


def _render(renderable: RenderableType) -> str:
    with console.capture() as capture:
        console.print(renderable)
    return capture.get()


def test_render_running_shows_pid() -> None:
    text = _render(render_daemon_status(DaemonStatus(running=True, pid=4242)))
    assert "running" in text
    assert "4242" in text


def test_render_stopped() -> None:
    text = _render(render_daemon_status(DaemonStatus(running=False, pid=None)))
    assert "stopped" in text
    assert "PID" not in text


def test_render_poll_progress_start_with_total() -> None:
    text = _render(render_poll_progress(ProgressEvent(phase="discovery", stage="start", total=3)))
    assert "discovery" in text
    assert "0/3" in text


def test_render_poll_progress_item_without_total() -> None:
    # The scoring phase has no total up front → "?" as the denominator.
    text = _render(
        render_poll_progress(
            ProgressEvent(phase="scoring", stage="item", label="BE x posting 1", done=1, total=None)
        )
    )
    assert "1/?" in text
    assert "BE x posting 1" in text


def test_render_poll_progress_item_with_total() -> None:
    text = _render(
        render_poll_progress(
            ProgressEvent(phase="aggregator", stage="item", label="remoteok", done=2, total=2)
        )
    )
    assert "2/2" in text


def test_render_poll_progress_done() -> None:
    text = _render(render_poll_progress(ProgressEvent(phase="scoring", stage="done", done=4)))
    assert "done" in text


def test_render_poll_result_plain() -> None:
    text = _render(
        render_poll_result(
            ResultEvent(discovered=1, scored=2, skipped=0, failed_sources=0, inactive=0, claimed=0)
        )
    )
    assert "Discovered" in text
    assert "Needs API key" not in text
    assert "Claimed" not in text


def test_render_poll_result_with_inactive_and_claimed() -> None:
    text = _render(
        render_poll_result(
            ResultEvent(discovered=1, scored=2, skipped=1, failed_sources=1, inactive=1, claimed=3)
        )
    )
    assert "Needs API key" in text
    assert "Claimed by another worker" in text
