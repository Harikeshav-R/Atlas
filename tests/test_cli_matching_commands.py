"""Tests for the ``atlas score`` command and ``atlas add`` scoring integration.

These drive the Typer commands through the ``CliRunner`` with every boundary
stubbed: an in-memory database engine, a no-op logging setup, a stubbed provider
chain, and a stubbed :func:`atlas.matching.service.score_posting` (its logic is
covered in ``test_matching_service``), so no real model call happens.
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
from atlas.matching.errors import NoActiveProfileError, ScoringError
from atlas.matching.service import ScoreOutcome
from atlas.matching.structure import DeterministicSignals, SalaryFit, SignalStatus
from atlas.scrape.errors import JobPostingNotFoundError
from atlas.scrape.service import AddOutcome

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
def _stub_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    """Stub config/secret/provider resolution so the commands build no real chain."""
    monkeypatch.setattr(app_module, "load_config", lambda: Config())
    monkeypatch.setattr(app_module, "default_secret_store", lambda: object())
    monkeypatch.setattr(app_module, "build_provider_chain", lambda ai, store: object())


def _outcome(*, score: int = 78, verdict: str = "good") -> ScoreOutcome:
    return ScoreOutcome(
        match_score_id=1,
        posting_id=1,
        title="Backend Engineer",
        company="Acme",
        score=score,
        verdict=verdict,
        salary_fit="within",
        rationale="Good overlap.",
        matched_strengths=["Python"],
        gaps=["Kubernetes"],
        dealbreaker_hits=[],
        signals=DeterministicSignals(salary=SalaryFit.WITHIN, location=SignalStatus.MATCH),
    )


# --- atlas score ----------------------------------------------------------------


def test_score_text_and_json(
    shared_engine: Engine, _stub_provider: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        app_module, "score_posting", lambda session, posting_id, *, provider: _outcome()
    )
    text = runner.invoke(app, ["score", "1"])
    assert text.exit_code == 0
    assert "Backend Engineer" in text.output
    assert "78/100" in text.output

    shown = runner.invoke(app, ["score", "1", "--json"])
    assert shown.exit_code == 0
    payload = json.loads(shown.output)
    assert payload["score"] == 78
    assert payload["verdict"] == "good"


def test_score_unknown_posting_exits_one(
    shared_engine: Engine, _stub_provider: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(session: object, posting_id: int, *, provider: object) -> ScoreOutcome:
        raise JobPostingNotFoundError(posting_id)

    monkeypatch.setattr(app_module, "score_posting", boom)
    result = runner.invoke(app, ["score", "999"])
    assert result.exit_code == 1
    assert "atlas score" in result.output


def test_score_no_profile_exits_one(
    shared_engine: Engine, _stub_provider: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(session: object, posting_id: int, *, provider: object) -> ScoreOutcome:
        raise NoActiveProfileError

    monkeypatch.setattr(app_module, "score_posting", boom)
    result = runner.invoke(app, ["score", "1"])
    assert result.exit_code == 1
    assert "atlas score" in result.output


def test_score_scoring_failure_exits_one(
    shared_engine: Engine, _stub_provider: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(session: object, posting_id: int, *, provider: object) -> ScoreOutcome:
        raise ScoringError("no usable assessment")

    monkeypatch.setattr(app_module, "score_posting", boom)
    result = runner.invoke(app, ["score", "1"])
    assert result.exit_code == 1
    assert "atlas score" in result.output


def test_score_reports_config_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def bad_config() -> object:
        raise ConfigError("no config")

    monkeypatch.setattr(app_module, "load_config", bad_config)
    result = runner.invoke(app, ["score", "1"])
    assert result.exit_code == 1
    assert "atlas score" in result.output


# --- atlas add scoring integration ----------------------------------------------


def test_add_scores_new_posting(
    shared_engine: Engine, _stub_provider: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        app_module,
        "add_posting",
        lambda session, url, *, provider: AddOutcome(
            posting_id=1, created=True, title="Backend Engineer", company="Acme"
        ),
    )
    monkeypatch.setattr(
        app_module, "score_posting", lambda session, posting_id, *, provider: _outcome(score=91)
    )
    result = runner.invoke(app, ["add", "https://jobs.acme.test/1"])
    assert result.exit_code == 0
    assert "Saved posting" in result.output
    assert "Fit:" in result.output
    assert "91" in result.output


def test_add_warns_when_scoring_unavailable(
    shared_engine: Engine, _stub_provider: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        app_module,
        "add_posting",
        lambda session, url, *, provider: AddOutcome(
            posting_id=1, created=True, title="Backend Engineer", company="Acme"
        ),
    )

    def boom(session: object, posting_id: int, *, provider: object) -> ScoreOutcome:
        raise NoActiveProfileError

    monkeypatch.setattr(app_module, "score_posting", boom)
    result = runner.invoke(app, ["add", "https://jobs.acme.test/1"])
    # The posting is still saved (exit 0); a muted hint points at `atlas score`.
    assert result.exit_code == 0
    assert "Saved posting" in result.output
    assert "not scored" in result.output


def test_add_noop_does_not_score(
    shared_engine: Engine, _stub_provider: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        app_module,
        "add_posting",
        lambda session, url, *, provider: AddOutcome(
            posting_id=5, created=False, title="Backend Engineer", company="Acme"
        ),
    )

    def fail(session: object, posting_id: int, *, provider: object) -> ScoreOutcome:
        raise AssertionError("scoring must not run for an already-added posting")

    monkeypatch.setattr(app_module, "score_posting", fail)
    result = runner.invoke(app, ["add", "https://jobs.acme.test/1"])
    assert result.exit_code == 0
    assert "Already added" in result.output
