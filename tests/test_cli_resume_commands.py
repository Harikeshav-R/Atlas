"""Tests for the ``atlas resume`` commands in :mod:`atlas.cli.main`.

These drive the Typer commands through the ``CliRunner`` with the boundaries
stubbed: an in-memory database engine (no real data dir) and a no-op logging
setup — the same monkeypatch idiom as the ``atlas profile`` command tests. The
resume file itself is a real ``tmp_path`` file so the read boundary is exercised.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest
from sqlmodel import SQLModel
from typer.testing import CliRunner

import atlas.cli.main as app_module
from atlas.cli.main import app
from atlas.db import create_db_engine

if TYPE_CHECKING:
    from pathlib import Path

    from sqlalchemy.engine import Engine

runner = CliRunner()

_MARKDOWN = "# Sam Carter\n\n## Skills\n\n- Python\n- Rust"


@pytest.fixture(autouse=True)
def _stub_logging(monkeypatch: pytest.MonkeyPatch) -> None:
    """Stub the callback's logging setup so no test writes a real log file."""
    monkeypatch.setattr(app_module, "setup_logging", lambda **kwargs: 0)


@pytest.fixture
def shared_engine(monkeypatch: pytest.MonkeyPatch) -> Engine:
    """Point the commands at one shared in-memory engine with the schema created.

    ``initialize_database`` is stubbed to return this engine, and its ``dispose``
    is neutered so the in-memory database survives across the command's teardown.
    """
    engine = create_db_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(engine, "dispose", lambda: None)
    monkeypatch.setattr(app_module, "initialize_database", lambda: engine)
    return engine


def _write(tmp_path: Path, content: str = _MARKDOWN) -> Path:
    path = tmp_path / "resume.md"
    path.write_text(content, encoding="utf-8")
    return path


def test_resume_set_creates_version(shared_engine: Engine, tmp_path: Path) -> None:
    result = runner.invoke(app, ["resume", "set", str(_write(tmp_path))])
    assert result.exit_code == 0
    assert "Saved master resume" in result.output
    assert "version 1" in result.output


def test_resume_set_unchanged_reports_no_change(shared_engine: Engine, tmp_path: Path) -> None:
    path = _write(tmp_path)
    runner.invoke(app, ["resume", "set", str(path)])
    result = runner.invoke(app, ["resume", "set", str(path)])
    assert result.exit_code == 0
    assert "No change" in result.output


def test_resume_set_changed_creates_next_version(shared_engine: Engine, tmp_path: Path) -> None:
    path = _write(tmp_path)
    runner.invoke(app, ["resume", "set", str(path)])
    path.write_text(_MARKDOWN + "\n- Go", encoding="utf-8")
    result = runner.invoke(app, ["resume", "set", str(path)])
    assert result.exit_code == 0
    assert "version 2" in result.output


def test_resume_set_missing_file_exits_one(shared_engine: Engine, tmp_path: Path) -> None:
    result = runner.invoke(app, ["resume", "set", str(tmp_path / "nope.md")])
    assert result.exit_code == 1
    assert "atlas resume set" in result.output


def test_resume_reparse_before_set_exits_one(shared_engine: Engine) -> None:
    result = runner.invoke(app, ["resume", "reparse"])
    assert result.exit_code == 1
    assert "atlas resume reparse" in result.output


def test_resume_reparse_after_set_versions(shared_engine: Engine, tmp_path: Path) -> None:
    runner.invoke(app, ["resume", "set", str(_write(tmp_path))])
    result = runner.invoke(app, ["resume", "reparse"])
    assert result.exit_code == 0
    assert "Reparsed master resume" in result.output
    assert "version 2" in result.output


def test_resume_show_text_and_json(shared_engine: Engine, tmp_path: Path) -> None:
    runner.invoke(app, ["resume", "set", str(_write(tmp_path))])
    text = runner.invoke(app, ["resume", "show"])
    assert text.exit_code == 0
    assert "Master resume versions" in text.output
    listed = runner.invoke(app, ["resume", "show", "--json"])
    assert listed.exit_code == 0
    payload = json.loads(listed.output)
    assert payload["latest_version"] == 1
    assert [v["version"] for v in payload["versions"]] == [1]


def test_resume_show_empty(shared_engine: Engine) -> None:
    result = runner.invoke(app, ["resume", "show"])
    assert result.exit_code == 0
    assert "No master resume yet" in result.output
