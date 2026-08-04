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
from atlas.cli.main import _quiet_console_logging, app
from atlas.db import create_db_engine

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
    """Point the command at one shared in-memory engine with the schema created."""
    engine = create_db_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(engine, "dispose", lambda: None)
    monkeypatch.setattr(app_module, "initialize_database", lambda: engine)
    return engine


class _FakeApp:
    """Records construction + ``run()`` so the command is tested without a terminal."""

    instances: ClassVar[list[_FakeApp]] = []

    def __init__(self, *, engine: Engine) -> None:
        self.engine = engine
        self.ran = False
        _FakeApp.instances.append(self)

    def run(self) -> None:
        self.ran = True


def test_tui_builds_app_and_runs(shared_engine: Engine, monkeypatch: pytest.MonkeyPatch) -> None:
    _FakeApp.instances.clear()
    # The command lazy-imports AtlasApp from atlas.tui.app; patch it there.
    import atlas.tui.app as tui_app_module

    monkeypatch.setattr(tui_app_module, "AtlasApp", _FakeApp)
    result = runner.invoke(app, ["tui"])
    assert result.exit_code == 0
    assert len(_FakeApp.instances) == 1
    instance = _FakeApp.instances[0]
    assert instance.engine is shared_engine
    assert instance.ran is True


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
