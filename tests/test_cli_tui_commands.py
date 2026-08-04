"""Tests for the ``atlas tui`` command in :mod:`atlas.cli.main`.

The command is driven through the ``CliRunner`` with the real Textual app
replaced by a fake, so no terminal is taken over: the test asserts the command
builds the app with the engine and invokes ``.run()`` once, mirroring how
``tests/test_main_entry.py`` covers the ``python -m atlas`` entry point.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, ClassVar

import pytest
from sqlmodel import SQLModel
from typer.testing import CliRunner

import atlas.cli.main as app_module
from atlas.ai.base import LLMError
from atlas.cli.main import _quiet_console_logging, app
from atlas.config.errors import ConfigError
from atlas.config.schema import Config
from atlas.db import create_db_engine

if TYPE_CHECKING:
    from pathlib import Path
    from typing import Any

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


class _FakeApp:
    """Records construction + ``run()`` so the command is tested without a terminal."""

    instances: ClassVar[list[_FakeApp]] = []

    def __init__(self, **kwargs: Any) -> None:
        self.kwargs = kwargs
        self.ran = False
        _FakeApp.instances.append(self)

    def run(self) -> None:
        self.ran = True


@pytest.fixture
def _fake_app(monkeypatch: pytest.MonkeyPatch) -> type[_FakeApp]:
    """Replace the real AtlasApp (lazy-imported by the command) with the recorder."""
    _FakeApp.instances.clear()
    import atlas.tui.app as tui_app_module

    monkeypatch.setattr(tui_app_module, "AtlasApp", _FakeApp)
    return _FakeApp


def _stub_action_builders(monkeypatch: pytest.MonkeyPatch, *, sentinel: object) -> None:
    """Make the boundary builders succeed, returning sentinels for provider/renderer."""
    monkeypatch.setattr(app_module, "load_config", Config)
    monkeypatch.setattr(app_module, "default_secret_store", lambda: object())
    monkeypatch.setattr(app_module, "build_provider_chain", lambda ai, store: sentinel)
    monkeypatch.setattr(app_module, "build_renderer", lambda render: sentinel)


def test_tui_builds_app_with_actions_and_runs(
    shared_engine: Engine, _fake_app: type[_FakeApp], monkeypatch: pytest.MonkeyPatch
) -> None:
    sentinel = object()
    _stub_action_builders(monkeypatch, sentinel=sentinel)
    result = runner.invoke(app, ["tui"])
    assert result.exit_code == 0
    assert len(_FakeApp.instances) == 1
    instance = _FakeApp.instances[0]
    assert instance.kwargs["engine"] is shared_engine
    # Action-capable: the built provider/renderer + config blocks were passed.
    assert instance.kwargs["provider"] is sentinel
    assert instance.kwargs["renderer"] is sentinel
    assert instance.kwargs["tailoring"] is not None
    assert instance.kwargs["render_config"] is not None
    assert instance.ran is True


def test_tui_falls_back_to_browse_only_on_config_error(
    shared_engine: Engine, _fake_app: type[_FakeApp], monkeypatch: pytest.MonkeyPatch
) -> None:
    def _bad_config() -> Config:
        raise ConfigError("no config")

    monkeypatch.setattr(app_module, "load_config", _bad_config)
    result = runner.invoke(app, ["tui"])
    assert result.exit_code == 0
    assert "atlas tui" in result.output  # the disabled hint printed
    instance = _FakeApp.instances[0]
    # Browse-only: no provider/renderer/config were passed.
    assert instance.kwargs["provider"] is None
    assert instance.kwargs["renderer"] is None
    assert instance.kwargs["tailoring"] is None
    assert instance.kwargs["render_config"] is None
    assert instance.ran is True


def test_tui_falls_back_to_browse_only_on_llm_error(
    shared_engine: Engine, _fake_app: type[_FakeApp], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(app_module, "load_config", Config)
    monkeypatch.setattr(app_module, "default_secret_store", lambda: object())

    def _bad_provider(ai: object, store: object) -> object:
        raise LLMError("no backend")

    monkeypatch.setattr(app_module, "build_provider_chain", _bad_provider)
    result = runner.invoke(app, ["tui"])
    assert result.exit_code == 0
    assert _FakeApp.instances[0].kwargs["provider"] is None
    assert _FakeApp.instances[0].ran is True


def test_quiet_console_logging_keeps_file_handler(tmp_path: Path) -> None:
    """The helper drops console handlers but keeps the file handler."""
    logger = logging.getLogger("atlas")

    # A console (StreamHandler) and a real file handler under tmp_path; the autouse
    # reset_atlas_logging fixture restores/closes handlers after the test.
    console_handler: logging.Handler = logging.StreamHandler()
    log_file = tmp_path / "atlas.log"
    file_handler = logging.FileHandler(log_file)
    logger.addHandler(console_handler)
    logger.addHandler(file_handler)

    _quiet_console_logging()

    assert console_handler not in logger.handlers
    assert file_handler in logger.handlers
    assert all(isinstance(h, logging.FileHandler) for h in logger.handlers)
