"""Tests for the ``atlas resume render`` command in :mod:`atlas.cli.main`.

These drive the Typer command through the ``CliRunner`` with every boundary
stubbed: an in-memory database engine, a no-op logging setup, a stubbed renderer,
and a stubbed :func:`atlas.render.service.render_master_resume` (its logic is
covered in ``test_render_service``), so no real WeasyPrint render happens.
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
from atlas.render.errors import NoMasterResumeError, RenderError
from atlas.render.service import RenderOutcome

if TYPE_CHECKING:
    from sqlalchemy.engine import Engine

runner = CliRunner()


@pytest.fixture(autouse=True)
def _stub_logging(monkeypatch: pytest.MonkeyPatch) -> None:
    """Stub the callback's logging setup so no test writes a real log file."""
    monkeypatch.setattr(app_module, "setup_logging", lambda **kwargs: 0)


@pytest.fixture
def shared_engine(monkeypatch: pytest.MonkeyPatch) -> Engine:
    """Point the command at one shared in-memory engine with the schema created."""
    engine = create_db_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(engine, "dispose", lambda: None)
    monkeypatch.setattr(app_module, "initialize_database", lambda: engine)
    return engine


@pytest.fixture
def _stub_render(monkeypatch: pytest.MonkeyPatch) -> None:
    """Stub config + renderer construction so the command builds no real renderer."""
    monkeypatch.setattr(app_module, "load_config", lambda: Config())
    monkeypatch.setattr(app_module, "build_renderer", lambda render_config: object())


def _outcome(*, page_count: int = 1, one_page: bool = True) -> RenderOutcome:
    return RenderOutcome(
        path="/data/renders/Sam_Lee__resume__v1.pdf",
        page_count=page_count,
        one_page=one_page,
        version=1,
        theme="jakes-resume",
    )


def test_render_text_and_json(
    shared_engine: Engine, _stub_render: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        app_module,
        "render_master_resume",
        lambda session, *, renderer, theme: _outcome(),
    )
    text = runner.invoke(app, ["resume", "render"])
    assert text.exit_code == 0
    assert "Sam_Lee__resume__v1.pdf" in text.output

    shown = runner.invoke(app, ["resume", "render", "--json"])
    assert shown.exit_code == 0
    payload = json.loads(shown.output)
    assert payload["version"] == 1
    assert payload["one_page"] is True


def test_render_no_resume_exits_one(
    shared_engine: Engine, _stub_render: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(session: object, *, renderer: object, theme: str) -> RenderOutcome:
        raise NoMasterResumeError

    monkeypatch.setattr(app_module, "render_master_resume", boom)
    result = runner.invoke(app, ["resume", "render"])
    assert result.exit_code == 1
    assert "atlas resume render" in result.output


def test_render_unsupported_engine_exits_one(
    shared_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    # build_renderer rejects an unsupported engine before the DB is touched.
    monkeypatch.setattr(app_module, "load_config", lambda: Config())

    def bad_engine(render_config: object) -> object:
        raise RenderError("Render engine 'chromium' is not supported yet.")

    monkeypatch.setattr(app_module, "build_renderer", bad_engine)
    result = runner.invoke(app, ["resume", "render"])
    assert result.exit_code == 1
    assert "atlas resume render" in result.output


def test_render_reports_config_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def bad_config() -> object:
        raise ConfigError("no config")

    monkeypatch.setattr(app_module, "load_config", bad_config)
    result = runner.invoke(app, ["resume", "render"])
    assert result.exit_code == 1
    assert "atlas resume render" in result.output
