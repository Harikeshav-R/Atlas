"""The daemon's scheduler seam (PROJECT.md §4.1, §13).

Following the house pattern for OS/heavy-dependency boundaries
(:mod:`atlas.ai.cli.runner`, :mod:`atlas.render.renderer`): a
``runtime_checkable`` :class:`Scheduler` protocol is the injectable interface,
the pure :func:`register_poll_job` wires a job onto it from config (tested against
a fake), and :func:`default_scheduler` — a thin ``# pragma: no cover`` factory —
lazily imports APScheduler and returns a real ``BlockingScheduler`` so the
hermetic suite never imports the scheduler stack.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from collections.abc import Callable

    from atlas.config.schema import DiscoveryConfig

__all__ = ["Scheduler", "default_scheduler", "register_poll_job"]


@runtime_checkable
class Scheduler(Protocol):
    """The minimal scheduler interface the daemon depends on.

    A subset of APScheduler's scheduler API — enough to register an interval job
    and run/stop the loop. Tests inject a fake; production uses
    :func:`default_scheduler`.
    """

    def add_job(self, func: Callable[[], None], trigger: str, **kwargs: object) -> object:
        """Register ``func`` to run on ``trigger`` (e.g. ``"interval"``)."""

    def start(self) -> None:
        """Start the scheduler (blocking for a ``BlockingScheduler``)."""

    def shutdown(self, *, wait: bool = True) -> None:
        """Stop the scheduler."""


def register_poll_job(
    scheduler: Scheduler,
    config: DiscoveryConfig,
    *,
    run: Callable[[], None],
) -> None:
    """Register the scoring poll on ``scheduler`` at the configured interval.

    Pure wiring (no scheduler start): schedules ``run`` on an ``interval`` trigger
    every ``config.poll_interval_minutes`` minutes. The interval is clamped to a
    minimum of one minute so a zero/negative config value can't produce an invalid
    trigger.

    Args:
        scheduler: The scheduler to register the job on.
        config: The ``[discovery]`` config supplying the poll interval.
        run: The zero-arg callable the job invokes (the bound scoring poll).
    """
    minutes = max(1, config.poll_interval_minutes)
    scheduler.add_job(run, "interval", minutes=minutes)


def default_scheduler() -> Scheduler:  # pragma: no cover - constructs the real APScheduler
    """Return a real blocking APScheduler.

    Carries ``# pragma: no cover`` because the hermetic suite never constructs the
    real scheduler (AGENTS.md §6.2); APScheduler is imported lazily here so the
    default test run never imports the scheduler stack. Tests inject a fake
    :class:`Scheduler` instead.
    """
    from apscheduler.schedulers.blocking import BlockingScheduler

    scheduler: Scheduler = BlockingScheduler()
    return scheduler
