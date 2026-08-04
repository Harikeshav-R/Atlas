"""Tests for the daemon-status rendering in :mod:`atlas.cli.daemon`."""

from __future__ import annotations

from rich.console import RenderableType

from atlas.cli.console import console
from atlas.cli.daemon import render_daemon_status
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
