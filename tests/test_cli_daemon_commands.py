"""Tests for the ``atlas daemon`` commands in :mod:`atlas.cli.main`.

Driven through the ``CliRunner`` with every boundary stubbed: an in-memory
engine, a no-op logging setup, a stubbed provider chain, a ``FakeScheduler`` in
place of the real APScheduler (so ``start`` never blocks), and a ``tmp_path``
pidfile. No real process, scheduler, or socket is touched (AGENTS.md §6.2).
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest
from sqlmodel import SQLModel
from typer.testing import CliRunner

import atlas.cli.main as app_module
from atlas.cli.main import app
from atlas.config.errors import ConfigError
from atlas.config.schema import Config
from atlas.daemon.service import write_pid
from atlas.db import create_db_engine
from tests.conftest import FakeProcessControl, FakeScheduler

if TYPE_CHECKING:
    from pathlib import Path

    from sqlalchemy.engine import Engine

runner = CliRunner()


@pytest.fixture(autouse=True)
def _stub_logging(monkeypatch: pytest.MonkeyPatch) -> None:
    """Stub the callback's logging setup so no test writes a real log file."""
    monkeypatch.setattr(app_module, "setup_logging", lambda **kwargs: 0)


@pytest.fixture
def shared_engine(monkeypatch: pytest.MonkeyPatch) -> Engine:
    """Point the commands at one shared in-memory engine with the schema created."""
    engine = create_db_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(engine, "dispose", lambda: None)
    monkeypatch.setattr(app_module, "initialize_database", lambda: engine)
    return engine


@pytest.fixture
def pid_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point the daemon commands at a tmp_path pidfile."""
    path = tmp_path / "daemon.pid"
    monkeypatch.setattr(app_module, "pid_file", lambda: path)
    return path


@pytest.fixture
def _stub_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    """Stub config/secret/provider resolution so ``start`` builds no real chain."""
    monkeypatch.setattr(app_module, "load_config", Config)
    monkeypatch.setattr(app_module, "default_secret_store", lambda: object())
    monkeypatch.setattr(app_module, "build_provider_chain", lambda ai, store: object())


# --- atlas daemon start ---------------------------------------------------------


def test_start_registers_job_and_starts(
    shared_engine: Engine, pid_path: Path, _stub_provider: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    scheduler = FakeScheduler()
    monkeypatch.setattr(app_module, "default_scheduler", lambda: scheduler)
    result = runner.invoke(app, ["daemon", "start"])
    assert result.exit_code == 0
    assert scheduler.started is True
    assert len(scheduler.jobs) == 1
    # The bound poll callable runs in its own session against the shared engine.
    scheduler.jobs[0][0]()  # no rows to score → no error


def test_start_reports_config_error(pid_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def _bad_config() -> Config:
        raise ConfigError("no config")

    monkeypatch.setattr(app_module, "load_config", _bad_config)
    result = runner.invoke(app, ["daemon", "start"])
    assert result.exit_code == 1
    assert "atlas daemon start" in result.output


def test_start_refuses_when_running(
    shared_engine: Engine, pid_path: Path, _stub_provider: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_pid(pid_path, 4242)
    monkeypatch.setattr(app_module, "default_scheduler", FakeScheduler)
    # Make the recorded pid look alive so start refuses.
    monkeypatch.setattr(
        "atlas.daemon.service.default_process_control", FakeProcessControl(alive={4242})
    )
    result = runner.invoke(app, ["daemon", "start"])
    assert result.exit_code == 1
    assert "already running" in result.output


# --- atlas daemon stop ----------------------------------------------------------


def test_stop_success(pid_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    write_pid(pid_path, 4242)
    monkeypatch.setattr(
        "atlas.daemon.service.default_process_control", FakeProcessControl(alive={4242})
    )
    result = runner.invoke(app, ["daemon", "stop"])
    assert result.exit_code == 0
    assert "Stopped the daemon" in result.output
    assert not pid_path.exists()


def test_stop_not_running_exits_one(pid_path: Path) -> None:
    result = runner.invoke(app, ["daemon", "stop"])
    assert result.exit_code == 1
    assert "atlas daemon stop" in result.output


# --- atlas daemon status --------------------------------------------------------


def test_status_stopped_text_and_json(pid_path: Path) -> None:
    text = runner.invoke(app, ["daemon", "status"])
    assert text.exit_code == 0
    assert "stopped" in text.output
    shown = runner.invoke(app, ["daemon", "status", "--json"])
    assert shown.exit_code == 0
    assert json.loads(shown.output) == {"running": False, "pid": None}


def test_status_running(pid_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    write_pid(pid_path, 4242)
    monkeypatch.setattr(
        "atlas.daemon.service.default_process_control", FakeProcessControl(alive={4242})
    )
    result = runner.invoke(app, ["daemon", "status", "--json"])
    assert result.exit_code == 0
    assert json.loads(result.output) == {"running": True, "pid": 4242}
