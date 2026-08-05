"""The Atlas background daemon (PROJECT.md §4.1).

A long-running process that runs Atlas's scheduled work. Today it runs a single
job — the **scoring poll** (:mod:`atlas.daemon.poll`), which clears the fit-score
backlog against the active profile — on an APScheduler interval
(:mod:`atlas.daemon.scheduler`). :mod:`atlas.daemon.service` owns the process
lifecycle (a PID file under the state dir, start/stop/status) behind an injectable
process-control seam, so everything but the real scheduler start and OS signals is
hermetically testable.

Discovery-source polling, the IPC surface for the TUI, and desktop notifications
(the rest of §4.1) join this package as later Phase 2 work.
"""

from __future__ import annotations

from atlas.daemon.errors import (
    DaemonAlreadyRunningError,
    DaemonError,
    DaemonNotRunningError,
)
from atlas.daemon.poll import PollOutcome, run_scoring_poll
from atlas.daemon.scheduler import Scheduler, default_scheduler, register_poll_job
from atlas.daemon.service import (
    DaemonStatus,
    ProcessControl,
    daemon_status,
    default_process_control,
    start_daemon,
    stop_daemon,
)

__all__ = [
    "DaemonAlreadyRunningError",
    "DaemonError",
    "DaemonNotRunningError",
    "DaemonStatus",
    "PollOutcome",
    "ProcessControl",
    "Scheduler",
    "daemon_status",
    "default_process_control",
    "default_scheduler",
    "register_poll_job",
    "run_scoring_poll",
    "start_daemon",
    "stop_daemon",
]
