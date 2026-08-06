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
from atlas.db import create_db_engine, session_scope
from atlas.discovery.repository import get_or_create_ats_source
from atlas.scrape.fetcher import FetchResult
from atlas.scrape.repository import get_or_create_company, list_postings
from tests.conftest import FakeFetcher, FakeIpcServer, FakeProcessControl, FakeScheduler

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence
    from pathlib import Path

    from sqlalchemy.engine import Engine

    from atlas.daemon.ipc import IpcEvent, IpcRequest

runner = CliRunner()


@pytest.fixture
def socket_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point the daemon commands at a tmp_path socket file (no real socket)."""
    path = tmp_path / "daemon.socket"
    monkeypatch.setattr(app_module, "socket_file", lambda: path)
    return path


@pytest.fixture
def _stub_ipc_server(monkeypatch: pytest.MonkeyPatch) -> None:
    """Stub the IPC server factory so ``start`` never binds a real socket."""
    monkeypatch.setattr(app_module, "default_ipc_server", FakeIpcServer)


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
    shared_engine: Engine,
    pid_path: Path,
    socket_path: Path,
    _stub_provider: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scheduler = FakeScheduler()
    monkeypatch.setattr(app_module, "default_scheduler", lambda: scheduler)
    ipc = FakeIpcServer()
    monkeypatch.setattr(app_module, "default_ipc_server", lambda: ipc)
    result = runner.invoke(app, ["daemon", "start"])
    assert result.exit_code == 0
    assert scheduler.started is True
    assert len(scheduler.jobs) == 1
    # The bound poll callable runs in its own session against the shared engine —
    # empty watchlist + empty backlog → no fetch, no error.
    scheduler.jobs[0][0]()
    # The dispatch the CLI wired into the IPC server services a live status
    # request against the daemon's own engine/config/owner.
    from atlas.daemon.ipc import IpcRequest, StatusEvent

    events: list[IpcEvent] = []
    assert callable(ipc.dispatch)
    ipc.dispatch(IpcRequest(action="status"), events.append)
    assert any(isinstance(e, StatusEvent) for e in events)


_BOARD = json.dumps(
    {
        "jobs": [
            {
                "id": 7,
                "title": "Backend Engineer",
                "absolute_url": "https://boards.greenhouse.io/acme/jobs/7",
                "location": {"name": "Remote"},
                "content": "&lt;p&gt;Build.&lt;/p&gt;",
            }
        ],
        "meta": {"total": 1},
    }
)


def test_start_bound_job_discovers_then_scores(
    shared_engine: Engine,
    pid_path: Path,
    socket_path: Path,
    _stub_provider: None,
    _stub_ipc_server: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A watchlisted board + an injected fetcher: the bound job discovers the
    # posting first (persisted), then the scoring poll runs over the new backlog.
    with session_scope(shared_engine) as session:
        company = get_or_create_company(session, name="Acme")
        assert company.id is not None
        get_or_create_ats_source(
            session, ats_type="greenhouse", board_token="acme", company_id=company.id
        )
    monkeypatch.setattr(
        app_module,
        "default_fetcher",
        FakeFetcher(
            FetchResult(url="x", status_code=200, content_type="application/json", body=_BOARD)
        ),
    )
    scheduler = FakeScheduler()
    monkeypatch.setattr(app_module, "default_scheduler", lambda: scheduler)
    result = runner.invoke(app, ["daemon", "start"])
    assert result.exit_code == 0
    scheduler.jobs[0][0]()
    with session_scope(shared_engine) as session:
        assert [p.external_id for p in list_postings(session)] == ["7"]


def test_start_reports_config_error(pid_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def _bad_config() -> Config:
        raise ConfigError("no config")

    monkeypatch.setattr(app_module, "load_config", _bad_config)
    result = runner.invoke(app, ["daemon", "start"])
    assert result.exit_code == 1
    assert "atlas daemon start" in result.output


def test_start_refuses_when_running(
    shared_engine: Engine,
    pid_path: Path,
    socket_path: Path,
    _stub_provider: None,
    _stub_ipc_server: None,
    monkeypatch: pytest.MonkeyPatch,
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


# --- atlas daemon poll ----------------------------------------------------------


def _scripted_ipc_request(
    events: Sequence[IpcEvent],
) -> Callable[..., None]:
    """Build a fake ``ipc_request`` that replays ``events`` to the ``on_event`` sink."""

    def fake(
        socket_path: Path,
        request: IpcRequest,
        *,
        on_event: Callable[[IpcEvent], None],
        connect: object = None,
    ) -> None:
        for event in events:
            on_event(event)

    return fake


def test_poll_streams_progress_and_result(
    socket_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from atlas.daemon.ipc import ProgressEvent, ResultEvent

    events: list[IpcEvent] = [
        ProgressEvent(phase="discovery", stage="start", total=1),
        ProgressEvent(phase="discovery", stage="item", label="greenhouse:acme", done=1, total=1),
        ResultEvent(discovered=1, scored=1, skipped=0, failed_sources=0, inactive=0, claimed=0),
    ]
    monkeypatch.setattr(app_module, "ipc_request", _scripted_ipc_request(events))
    result = runner.invoke(app, ["daemon", "poll"])
    assert result.exit_code == 0
    assert "Discovered" in result.output


def test_poll_json(socket_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from atlas.daemon.ipc import ResultEvent

    events: list[IpcEvent] = [
        ResultEvent(discovered=2, scored=1, skipped=0, failed_sources=0, inactive=1, claimed=0)
    ]
    monkeypatch.setattr(app_module, "ipc_request", _scripted_ipc_request(events))
    result = runner.invoke(app, ["daemon", "poll", "--json"])
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["discovered"] == 2
    assert payload["inactive"] == 1


def test_poll_reports_error_event(socket_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from atlas.daemon.ipc import ErrorEvent

    events: list[IpcEvent] = [ErrorEvent(message="the poll failed")]
    monkeypatch.setattr(app_module, "ipc_request", _scripted_ipc_request(events))
    result = runner.invoke(app, ["daemon", "poll"])
    assert result.exit_code == 1
    assert "the poll failed" in result.output


def test_poll_daemon_not_running_exits_one(
    socket_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from atlas.daemon.errors import IpcUnavailableError

    def refuse(
        _socket_path: Path, _request: IpcRequest, *, on_event: object, connect: object = None
    ) -> None:
        raise IpcUnavailableError

    monkeypatch.setattr(app_module, "ipc_request", refuse)
    result = runner.invoke(app, ["daemon", "poll"])
    assert result.exit_code == 1
    assert "atlas daemon poll" in result.output
