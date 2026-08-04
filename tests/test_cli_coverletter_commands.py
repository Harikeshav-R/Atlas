"""Tests for the ``atlas cover`` command in :mod:`atlas.cli.main`.

These drive the Typer command through the ``CliRunner`` with every boundary
stubbed (in-memory engine, no-op logging, stubbed provider + renderer, stubbed
:func:`atlas.coverletter.service.write_application_cover_letter`), so no real model
call or WeasyPrint render happens.
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
from atlas.coverletter.errors import CoverLetterOutputError, NoActiveProfileError
from atlas.coverletter.service import CoverLetterOutcome
from atlas.db import create_db_engine
from atlas.scrape.errors import JobPostingNotFoundError

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


def _outcome() -> CoverLetterOutcome:
    return CoverLetterOutcome(
        application_id=1,
        cover_letter_id=1,
        version=1,
        posting_id=1,
        title="Backend Engineer",
        company="Globex",
        path="/data/renders/Sam__Globex__cover.pdf",
        page_count=1,
        one_page=True,
        tone="professional",
        grounded_on="master_resume",
        gaps=["Kubernetes"],
    )


def test_cover_text_and_json(
    shared_engine: Engine, _stub_collaborators: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        app_module,
        "write_application_cover_letter",
        lambda session, job_id, **kwargs: _outcome(),
    )
    text = runner.invoke(app, ["cover", "1"])
    assert text.exit_code == 0
    assert "Backend Engineer" in text.output

    shown = runner.invoke(app, ["cover", "1", "--json"])
    assert shown.exit_code == 0
    payload = json.loads(shown.output)
    assert payload["version"] == 1
    assert payload["grounded_on"] == "master_resume"


def test_cover_passes_tone(
    shared_engine: Engine, _stub_collaborators: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: dict[str, object] = {}

    def _capture(session: object, job_id: int, **kwargs: object) -> CoverLetterOutcome:
        seen.update(kwargs)
        return _outcome()

    monkeypatch.setattr(app_module, "write_application_cover_letter", _capture)
    result = runner.invoke(app, ["cover", "1", "--tone", "warm"])
    assert result.exit_code == 0
    assert seen["tone"] == "warm"


def test_cover_unknown_posting_exits_one(
    shared_engine: Engine, _stub_collaborators: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(session: object, job_id: int, **kwargs: object) -> CoverLetterOutcome:
        raise JobPostingNotFoundError(job_id)

    monkeypatch.setattr(app_module, "write_application_cover_letter", boom)
    result = runner.invoke(app, ["cover", "999"])
    assert result.exit_code == 1
    assert "atlas cover" in result.output


def test_cover_no_profile_exits_one(
    shared_engine: Engine, _stub_collaborators: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(session: object, job_id: int, **kwargs: object) -> CoverLetterOutcome:
        raise NoActiveProfileError

    monkeypatch.setattr(app_module, "write_application_cover_letter", boom)
    result = runner.invoke(app, ["cover", "1"])
    assert result.exit_code == 1
    assert "atlas cover" in result.output


def test_cover_output_error_exits_one(
    shared_engine: Engine, _stub_collaborators: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(session: object, job_id: int, **kwargs: object) -> CoverLetterOutcome:
        raise CoverLetterOutputError("no usable letter")

    monkeypatch.setattr(app_module, "write_application_cover_letter", boom)
    result = runner.invoke(app, ["cover", "1"])
    assert result.exit_code == 1
    assert "atlas cover" in result.output


def test_cover_reports_config_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def bad_config() -> object:
        raise ConfigError("no config")

    monkeypatch.setattr(app_module, "load_config", bad_config)
    result = runner.invoke(app, ["cover", "1"])
    assert result.exit_code == 1
    assert "atlas cover" in result.output
