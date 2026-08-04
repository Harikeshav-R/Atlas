"""Tests for the ``atlas render`` / ``atlas open`` commands in :mod:`atlas.cli.main`.

These drive the Typer commands through the ``CliRunner`` with every boundary
stubbed (in-memory engine, no-op logging, stubbed renderer / services), so no real
render or file-open happens.
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
from atlas.db import create_db_engine
from atlas.materials.service import OpenOutcome, RerenderOutcome
from atlas.platform.opener import FileOpenError
from atlas.tailor.errors import ApplicationNotFoundError

if TYPE_CHECKING:
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
def _stub_renderer(monkeypatch: pytest.MonkeyPatch) -> None:
    """Stub config + renderer construction so `atlas render` builds nothing real."""
    monkeypatch.setattr(app_module, "load_config", lambda: Config())
    monkeypatch.setattr(app_module, "build_renderer", lambda render_config: object())


# --- atlas render ---------------------------------------------------------------


def test_render_text_and_json(
    shared_engine: Engine, _stub_renderer: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    outcome = RerenderOutcome(
        application_id=1, resume_path="/data/renders/r.pdf", cover_letter_path="/data/renders/c.pdf"
    )
    monkeypatch.setattr(
        app_module, "rerender_application", lambda session, app_id, **kwargs: outcome
    )
    text = runner.invoke(app, ["render", "1"])
    assert text.exit_code == 0
    assert "r.pdf" in text.output

    shown = runner.invoke(app, ["render", "1", "--json"])
    assert shown.exit_code == 0
    payload = json.loads(shown.output)
    assert payload["resume_path"] == "/data/renders/r.pdf"


def test_render_unknown_application_exits_one(
    shared_engine: Engine, _stub_renderer: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(session: object, app_id: int, **kwargs: object) -> RerenderOutcome:
        raise ApplicationNotFoundError(app_id)

    monkeypatch.setattr(app_module, "rerender_application", boom)
    result = runner.invoke(app, ["render", "999"])
    assert result.exit_code == 1
    assert "atlas render" in result.output


def test_render_reports_config_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def bad_config() -> object:
        raise ConfigError("no config")

    monkeypatch.setattr(app_module, "load_config", bad_config)
    result = runner.invoke(app, ["render", "1"])
    assert result.exit_code == 1
    assert "atlas render" in result.output


# --- atlas open -----------------------------------------------------------------


def test_open_text_and_json(shared_engine: Engine, monkeypatch: pytest.MonkeyPatch) -> None:
    outcome = OpenOutcome(application_id=1, opened=["/data/renders/r.pdf"])
    monkeypatch.setattr(app_module, "open_application", lambda session, app_id, **kwargs: outcome)
    text = runner.invoke(app, ["open", "1"])
    assert text.exit_code == 0
    assert "r.pdf" in text.output

    shown = runner.invoke(app, ["open", "1", "--json"])
    assert shown.exit_code == 0
    payload = json.loads(shown.output)
    assert payload["opened"] == ["/data/renders/r.pdf"]


def test_open_unknown_application_exits_one(
    shared_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(session: object, app_id: int, **kwargs: object) -> OpenOutcome:
        raise ApplicationNotFoundError(app_id)

    monkeypatch.setattr(app_module, "open_application", boom)
    result = runner.invoke(app, ["open", "999"])
    assert result.exit_code == 1
    assert "atlas open" in result.output


def test_open_file_open_error_exits_one(
    shared_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(session: object, app_id: int, **kwargs: object) -> OpenOutcome:
        raise FileOpenError("could not open")

    monkeypatch.setattr(app_module, "open_application", boom)
    result = runner.invoke(app, ["open", "1"])
    assert result.exit_code == 1
    assert "atlas open" in result.output
