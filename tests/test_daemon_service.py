"""Tests for the daemon lifecycle in :mod:`atlas.daemon.service`.

Uses a ``tmp_path`` pidfile, a ``FakeProcessControl`` (no real OS processes), and
a ``FakeScheduler`` (never blocks) so the whole start/stop/status flow is
hermetic (AGENTS.md §6.2).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from atlas.config.schema import DiscoveryConfig
from atlas.daemon.errors import DaemonAlreadyRunningError, DaemonNotRunningError
from atlas.daemon.service import (
    ProcessControl,
    daemon_status,
    default_process_control,
    read_pid,
    start_daemon,
    stop_daemon,
    write_pid,
)
from tests.conftest import FakeIpcServer, FakeProcessControl, FakeScheduler

if TYPE_CHECKING:
    from pathlib import Path

    from atlas.daemon.ipc import IpcRequest


def _noop_dispatch(_request: IpcRequest, _emit: object) -> None:
    """A dispatch that does nothing (the lifecycle tests don't exercise handling)."""


def test_write_then_read_pid_round_trip(tmp_path: Path) -> None:
    pid_path = tmp_path / "sub" / "daemon.pid"  # parent created by write_pid
    write_pid(pid_path, 1234)
    assert read_pid(pid_path) == 1234


def test_read_pid_missing_file(tmp_path: Path) -> None:
    assert read_pid(tmp_path / "absent.pid") is None


def test_read_pid_corrupt_file(tmp_path: Path) -> None:
    pid_path = tmp_path / "daemon.pid"
    pid_path.write_text("not-a-number", encoding="utf-8")
    assert read_pid(pid_path) is None


def test_default_process_control_conforms() -> None:
    assert isinstance(default_process_control, ProcessControl)
    assert default_process_control.current_pid() > 0


def test_status_stopped_when_no_pidfile(tmp_path: Path) -> None:
    status = daemon_status(tmp_path / "daemon.pid", control=FakeProcessControl())
    assert status.running is False
    assert status.pid is None


def test_status_stopped_when_stale(tmp_path: Path) -> None:
    pid_path = tmp_path / "daemon.pid"
    write_pid(pid_path, 9999)
    # 9999 is not in the alive set → stale pidfile → reported stopped.
    status = daemon_status(pid_path, control=FakeProcessControl(alive=set()))
    assert status.running is False


def test_status_running(tmp_path: Path) -> None:
    pid_path = tmp_path / "daemon.pid"
    write_pid(pid_path, 4242)
    status = daemon_status(pid_path, control=FakeProcessControl(alive={4242}))
    assert status.running is True
    assert status.pid == 4242


def test_start_writes_pid_and_starts_scheduler(tmp_path: Path) -> None:
    pid_path = tmp_path / "daemon.pid"
    scheduler = FakeScheduler()
    control = FakeProcessControl(pid=555)
    ticks: list[int] = []
    start_daemon(
        pid_path,
        DiscoveryConfig(poll_interval_minutes=30),
        scheduler=scheduler,
        run=lambda: ticks.append(1),
        control=control,
    )
    assert read_pid(pid_path) == 555
    assert scheduler.started is True
    assert len(scheduler.jobs) == 1
    assert scheduler.jobs[0][2] == {"minutes": 30}


def test_start_refuses_when_already_running(tmp_path: Path) -> None:
    pid_path = tmp_path / "daemon.pid"
    write_pid(pid_path, 4242)
    scheduler = FakeScheduler()
    with pytest.raises(DaemonAlreadyRunningError) as info:
        start_daemon(
            pid_path,
            DiscoveryConfig(),
            scheduler=scheduler,
            run=lambda: None,
            control=FakeProcessControl(alive={4242}),
        )
    assert info.value.pid == 4242
    assert scheduler.started is False  # never started


def test_start_overwrites_stale_pidfile(tmp_path: Path) -> None:
    pid_path = tmp_path / "daemon.pid"
    write_pid(pid_path, 9999)  # stale — not alive
    scheduler = FakeScheduler()
    start_daemon(
        pid_path,
        DiscoveryConfig(),
        scheduler=scheduler,
        run=lambda: None,
        control=FakeProcessControl(pid=777, alive=set()),
    )
    assert read_pid(pid_path) == 777
    assert scheduler.started is True


def test_start_serves_ipc_before_scheduler_and_stops_after(tmp_path: Path) -> None:
    pid_path = tmp_path / "daemon.pid"
    socket_path = tmp_path / "daemon.socket"
    order: list[str] = []

    class _RecordingIpcServer(FakeIpcServer):
        def serve(self, socket_path: Path, dispatch: object) -> None:
            order.append("ipc.serve")
            super().serve(socket_path, dispatch)

    class _RecordingScheduler(FakeScheduler):
        def start(self) -> None:
            order.append("scheduler.start")
            super().start()

    ipc = _RecordingIpcServer()
    start_daemon(
        pid_path,
        DiscoveryConfig(),
        scheduler=_RecordingScheduler(),
        run=lambda: None,
        control=FakeProcessControl(pid=1),
        ipc_server=ipc,
        dispatch=_noop_dispatch,
        socket_path=socket_path,
    )
    assert order == ["ipc.serve", "scheduler.start"]
    assert ipc.served == [socket_path]
    assert ipc.stopped is True  # stopped after the (fake, non-blocking) scheduler returns


def test_start_unlinks_stale_socket_before_serving(tmp_path: Path) -> None:
    pid_path = tmp_path / "daemon.pid"
    socket_path = tmp_path / "daemon.socket"
    socket_path.write_text("stale", encoding="utf-8")  # a leftover socket file
    ipc = FakeIpcServer()
    start_daemon(
        pid_path,
        DiscoveryConfig(),
        scheduler=FakeScheduler(),
        run=lambda: None,
        control=FakeProcessControl(pid=1),
        ipc_server=ipc,
        dispatch=_noop_dispatch,
        socket_path=socket_path,
    )
    # The stale file was removed before serve (the fake never re-creates it).
    assert not socket_path.exists()
    assert ipc.served == [socket_path]


def test_start_without_ipc_skips_serving(tmp_path: Path) -> None:
    # The plain lifecycle path (no IPC args) still starts the scheduler.
    pid_path = tmp_path / "daemon.pid"
    scheduler = FakeScheduler()
    start_daemon(
        pid_path,
        DiscoveryConfig(),
        scheduler=scheduler,
        run=lambda: None,
        control=FakeProcessControl(pid=1),
    )
    assert scheduler.started is True


def test_stop_signals_and_clears(tmp_path: Path) -> None:
    pid_path = tmp_path / "daemon.pid"
    write_pid(pid_path, 4242)
    control = FakeProcessControl(alive={4242})
    pid = stop_daemon(pid_path, control=control)
    assert pid == 4242
    assert control.terminated == [4242]
    assert not pid_path.exists()  # pidfile cleared


def test_stop_not_running_raises_and_clears_stale(tmp_path: Path) -> None:
    pid_path = tmp_path / "daemon.pid"
    write_pid(pid_path, 9999)  # stale
    with pytest.raises(DaemonNotRunningError):
        stop_daemon(pid_path, control=FakeProcessControl(alive=set()))
    assert not pid_path.exists()  # stale pidfile removed


def test_stop_no_pidfile_raises(tmp_path: Path) -> None:
    with pytest.raises(DaemonNotRunningError):
        stop_daemon(tmp_path / "absent.pid", control=FakeProcessControl())
