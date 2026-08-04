"""Tests for the daemon scheduler wiring in :mod:`atlas.daemon.scheduler`.

Exercises the pure ``register_poll_job`` against a ``FakeScheduler`` — the real
``default_scheduler`` (which constructs APScheduler) is pragma'd and never run in
the suite (AGENTS.md §6.2).
"""

from __future__ import annotations

from atlas.config.schema import DiscoveryConfig
from atlas.daemon.scheduler import Scheduler, register_poll_job
from tests.conftest import FakeScheduler


def test_register_poll_job_uses_configured_interval() -> None:
    scheduler = FakeScheduler()
    calls: list[int] = []
    register_poll_job(
        scheduler, DiscoveryConfig(poll_interval_minutes=45), run=lambda: calls.append(1)
    )
    assert len(scheduler.jobs) == 1
    func, trigger, kwargs = scheduler.jobs[0]
    assert trigger == "interval"
    assert kwargs == {"minutes": 45}
    # The registered callable is the one we passed.
    func()
    assert calls == [1]


def test_register_poll_job_clamps_to_one_minute() -> None:
    scheduler = FakeScheduler()
    register_poll_job(scheduler, DiscoveryConfig(poll_interval_minutes=0), run=lambda: None)
    _, _, kwargs = scheduler.jobs[0]
    assert kwargs == {"minutes": 1}


def test_fake_scheduler_conforms_to_protocol() -> None:
    assert isinstance(FakeScheduler(), Scheduler)
