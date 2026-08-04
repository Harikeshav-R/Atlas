"""Daemon lifecycle orchestration (PROJECT.md §4.1).

Owns the daemon's run-state: a PID file under the state dir records the running
process so ``atlas daemon status`` / ``stop`` can find it. The OS-touching pieces
— reading the current pid, probing liveness, signalling termination — sit behind
an injectable :class:`ProcessControl` seam (mirroring the :class:`FileOpener` /
``SubprocessRunner`` boundaries) whose real implementation is ``# pragma: no
cover``; everything else (pidfile read/write, start/stop/status orchestration) is
pure and tested with a fake.

Starting the daemon registers the scoring poll (:mod:`atlas.daemon.poll`) on a
scheduler (:mod:`atlas.daemon.scheduler`) and runs it; the blocking
``scheduler.start()`` is the only real edge in :func:`start_daemon`.
"""

from __future__ import annotations

import os
import signal
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from pydantic import BaseModel

from atlas.daemon.errors import DaemonAlreadyRunningError, DaemonNotRunningError
from atlas.daemon.scheduler import register_poll_job

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from atlas.config.schema import DiscoveryConfig
    from atlas.daemon.scheduler import Scheduler

__all__ = [
    "DaemonStatus",
    "ProcessControl",
    "daemon_status",
    "default_process_control",
    "read_pid",
    "start_daemon",
    "stop_daemon",
    "write_pid",
]


class DaemonStatus(BaseModel):
    """The result of ``atlas daemon status``.

    Attributes:
        running: Whether a live daemon process was found.
        pid: The daemon's process id when running, else ``None``.
    """

    running: bool
    pid: int | None


@runtime_checkable
class ProcessControl(Protocol):
    """The OS process operations the daemon lifecycle needs (injectable seam).

    Tests inject a fake that records calls and reports scripted liveness;
    production uses :func:`default_process_control`.
    """

    def current_pid(self) -> int:
        """Return the current process id."""

    def is_running(self, pid: int) -> bool:
        """Return whether a process with ``pid`` is alive."""

    def terminate(self, pid: int) -> None:
        """Ask the process ``pid`` to terminate."""


class _DefaultProcessControl:
    """The real :class:`ProcessControl`, backed by :mod:`os`/:mod:`signal`."""

    def current_pid(self) -> int:
        """Return this process's id."""
        return os.getpid()

    def is_running(self, pid: int) -> bool:  # pragma: no cover - probes a real OS process
        """Return whether ``pid`` is alive, via a zero signal (no-op probe)."""
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            # The process exists but is owned by someone else — treat as alive.
            return True
        return True

    def terminate(self, pid: int) -> None:  # pragma: no cover - signals a real OS process
        """Send ``SIGTERM`` to ``pid`` so the daemon shuts down cleanly."""
        os.kill(pid, signal.SIGTERM)


#: The production process-control implementation (real ``os``/``signal`` calls).
default_process_control: ProcessControl = _DefaultProcessControl()


def read_pid(pid_path: Path) -> int | None:
    """Return the pid recorded in ``pid_path``, or ``None`` if absent/unreadable.

    A missing file means "not running"; a corrupt (non-integer) file is treated
    the same way rather than raising, so a stale/garbled pidfile never wedges the
    CLI.
    """
    try:
        text = pid_path.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    try:
        return int(text)
    except ValueError:
        return None


def write_pid(pid_path: Path, pid: int) -> None:
    """Write ``pid`` to ``pid_path``, creating the parent directory if needed."""
    pid_path.parent.mkdir(parents=True, exist_ok=True)
    pid_path.write_text(str(pid), encoding="utf-8")


def daemon_status(pid_path: Path, *, control: ProcessControl | None = None) -> DaemonStatus:
    """Report whether a live daemon is running, per the pidfile.

    A pidfile whose process is no longer alive (stale) reports ``running=False``.
    ``control`` defaults to :data:`default_process_control`, resolved at call time
    so tests can substitute a fake.
    """
    control = control or default_process_control
    pid = read_pid(pid_path)
    if pid is None or not control.is_running(pid):
        return DaemonStatus(running=False, pid=None)
    return DaemonStatus(running=True, pid=pid)


def stop_daemon(pid_path: Path, *, control: ProcessControl | None = None) -> int:
    """Stop the running daemon and clear its pidfile; return the stopped pid.

    Raises:
        DaemonNotRunningError: If no live daemon is recorded.
    """
    control = control or default_process_control
    pid = read_pid(pid_path)
    if pid is None or not control.is_running(pid):
        pid_path.unlink(missing_ok=True)  # clear a stale pidfile if present
        raise DaemonNotRunningError
    control.terminate(pid)
    pid_path.unlink(missing_ok=True)
    return pid


def start_daemon(
    pid_path: Path,
    config: DiscoveryConfig,
    *,
    scheduler: Scheduler,
    run: Callable[[], None],
    control: ProcessControl | None = None,
) -> None:
    """Register the poll job and run the scheduler, recording the pid.

    Refuses to start if a live daemon is already recorded. Writes this process's
    pid, registers the scoring poll at the configured interval, then starts the
    scheduler (blocking). All orchestration up to the blocking start is tested with
    a fake scheduler + fake control; only ``scheduler.start()`` is a real edge.
    ``control`` defaults to :data:`default_process_control`, resolved at call time.

    Raises:
        DaemonAlreadyRunningError: If a live daemon is already recorded.
    """
    control = control or default_process_control
    existing = read_pid(pid_path)
    if existing is not None and control.is_running(existing):
        raise DaemonAlreadyRunningError(existing)
    write_pid(pid_path, control.current_pid())
    register_poll_job(scheduler, config, run=run)
    scheduler.start()
