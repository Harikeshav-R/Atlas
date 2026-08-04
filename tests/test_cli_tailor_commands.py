"""Tests for the ``atlas tailor`` command in :mod:`atlas.cli.main`.

These drive the Typer command through the ``CliRunner`` with every boundary
stubbed: an in-memory database engine, a no-op logging setup, a stubbed provider
chain + renderer, and a stubbed :func:`atlas.tailor.service.tailor_posting` (its
logic is covered in ``test_tailor_service``), so no real model call or WeasyPrint
render happens.
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
from atlas.scrape.errors import JobPostingNotFoundError
from atlas.tailor.errors import NoActiveProfileError, TailoringOutputError
from atlas.tailor.service import TailorOutcome

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
def _stub_collaborators(monkeypatch: pytest.MonkeyPatch) -> None:
    """Stub config/provider/renderer construction so the command builds nothing real."""
    monkeypatch.setattr(app_module, "load_config", lambda: Config())
    monkeypatch.setattr(app_module, "default_secret_store", lambda: object())
    monkeypatch.setattr(app_module, "build_provider_chain", lambda ai, store: object())
    monkeypatch.setattr(app_module, "build_renderer", lambda render_config: object())


def _outcome() -> TailorOutcome:
    return TailorOutcome(
        application_id=1,
        tailored_resume_id=1,
        version=1,
        posting_id=1,
        title="Backend Engineer",
        company="Globex",
        path="/data/renders/Sam__Globex__tailored.pdf",
        page_count=1,
        one_page=True,
        included_count=5,
        trimmed=0,
        gaps=["Kubernetes"],
    )


def test_tailor_text_and_json(
    shared_engine: Engine, _stub_collaborators: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        app_module,
        "tailor_posting",
        lambda session, job_id, **kwargs: _outcome(),
    )
    text = runner.invoke(app, ["tailor", "1"])
    assert text.exit_code == 0
    assert "Backend Engineer" in text.output

    shown = runner.invoke(app, ["tailor", "1", "--json"])
    assert shown.exit_code == 0
    payload = json.loads(shown.output)
    assert payload["version"] == 1
    assert payload["one_page"] is True


def test_tailor_unknown_posting_exits_one(
    shared_engine: Engine, _stub_collaborators: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(session: object, job_id: int, **kwargs: object) -> TailorOutcome:
        raise JobPostingNotFoundError(job_id)

    monkeypatch.setattr(app_module, "tailor_posting", boom)
    result = runner.invoke(app, ["tailor", "999"])
    assert result.exit_code == 1
    assert "atlas tailor" in result.output


def test_tailor_no_profile_exits_one(
    shared_engine: Engine, _stub_collaborators: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(session: object, job_id: int, **kwargs: object) -> TailorOutcome:
        raise NoActiveProfileError

    monkeypatch.setattr(app_module, "tailor_posting", boom)
    result = runner.invoke(app, ["tailor", "1"])
    assert result.exit_code == 1
    assert "atlas tailor" in result.output


def test_tailor_output_error_exits_one(
    shared_engine: Engine, _stub_collaborators: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(session: object, job_id: int, **kwargs: object) -> TailorOutcome:
        raise TailoringOutputError("no usable tailored resume")

    monkeypatch.setattr(app_module, "tailor_posting", boom)
    result = runner.invoke(app, ["tailor", "1"])
    assert result.exit_code == 1
    assert "atlas tailor" in result.output


def test_tailor_reports_config_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def bad_config() -> object:
        raise ConfigError("no config")

    monkeypatch.setattr(app_module, "load_config", bad_config)
    result = runner.invoke(app, ["tailor", "1"])
    assert result.exit_code == 1
    assert "atlas tailor" in result.output
