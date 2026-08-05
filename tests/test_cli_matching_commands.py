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
from atlas.db import create_db_engine, session_scope
from atlas.matching.errors import ScoringError
from atlas.matching.service import ScoreOutcome
from atlas.matching.structure import DeterministicSignals, SalaryFit, SignalStatus
from atlas.profiles.preferences import ProfilePreferences
from atlas.profiles.repository import create_profile
from atlas.scrape.errors import JobPostingNotFoundError
from atlas.scrape.service import AddOutcome

if TYPE_CHECKING:
    from sqlalchemy.engine import Engine

runner = CliRunner()


def _seed_active_profile(engine: Engine) -> int:
    """Create an active profile so the score/add commands can resolve one."""
    with session_scope(engine) as session:
        profile = create_profile(session, name="BE", preferences=ProfilePreferences(), active=True)
        assert profile.id is not None
        return profile.id


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
    _seed_active_profile(shared_engine)
    monkeypatch.setattr(
        app_module, "score_posting", lambda session, posting_id, *, profile, provider: _outcome()
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


def test_score_with_profile_option(
    shared_engine: Engine, _stub_provider: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    # --profile <id> scores against that profile; the id is passed through.
    profile_id = _seed_active_profile(shared_engine)
    captured: dict[str, int] = {}

    def _capture(
        session: object, posting_id: int, *, profile: object, provider: object
    ) -> ScoreOutcome:
        captured["profile_id"] = profile.id  # type: ignore[attr-defined]
        return _outcome()

    monkeypatch.setattr(app_module, "score_posting", _capture)
    result = runner.invoke(app, ["score", "1", "--profile", str(profile_id)])
    assert result.exit_code == 0
    assert captured["profile_id"] == profile_id


def test_score_unknown_profile_exits_one(
    shared_engine: Engine, _stub_provider: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A --profile id with no matching profile → exit 1 (never calls score_posting).
    monkeypatch.setattr(
        app_module,
        "score_posting",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not score")),
    )
    result = runner.invoke(app, ["score", "1", "--profile", "999"])
    assert result.exit_code == 1
    assert "atlas score" in result.output


def test_score_unknown_posting_exits_one(
    shared_engine: Engine, _stub_provider: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed_active_profile(shared_engine)

    def boom(
        session: object, posting_id: int, *, profile: object, provider: object
    ) -> ScoreOutcome:
        raise JobPostingNotFoundError(posting_id)

    monkeypatch.setattr(app_module, "score_posting", boom)
    result = runner.invoke(app, ["score", "999"])
    assert result.exit_code == 1
    assert "atlas score" in result.output


def test_score_no_active_profile_exits_one(
    shared_engine: Engine, _stub_provider: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    # No active profile in the DB → the command errors before scoring.
    monkeypatch.setattr(
        app_module,
        "score_posting",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not score")),
    )
    result = runner.invoke(app, ["score", "1"])
    assert result.exit_code == 1
    assert "atlas score" in result.output


def test_score_scoring_failure_exits_one(
    shared_engine: Engine, _stub_provider: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed_active_profile(shared_engine)

    def boom(
        session: object, posting_id: int, *, profile: object, provider: object
    ) -> ScoreOutcome:
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
    _seed_active_profile(shared_engine)
    monkeypatch.setattr(
        app_module,
        "add_posting",
        lambda session, url, *, provider: AddOutcome(
            posting_id=1, created=True, title="Backend Engineer", company="Acme"
        ),
    )
    monkeypatch.setattr(
        app_module,
        "score_posting",
        lambda session, posting_id, *, profile, provider: _outcome(score=91),
    )
    result = runner.invoke(app, ["add", "https://jobs.acme.test/1"])
    assert result.exit_code == 0
    assert "Saved posting" in result.output
    assert "Fit:" in result.output
    assert "91" in result.output


def test_add_warns_when_no_active_profile(
    shared_engine: Engine, _stub_provider: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    # No active profile → _score_after_add resolves none and prints a muted hint.
    monkeypatch.setattr(
        app_module,
        "add_posting",
        lambda session, url, *, provider: AddOutcome(
            posting_id=1, created=True, title="Backend Engineer", company="Acme"
        ),
    )
    monkeypatch.setattr(
        app_module,
        "score_posting",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not score")),
    )
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

    def fail(
        session: object, posting_id: int, *, profile: object, provider: object
    ) -> ScoreOutcome:
        raise AssertionError("scoring must not run for an already-added posting")

    monkeypatch.setattr(app_module, "score_posting", fail)
    result = runner.invoke(app, ["add", "https://jobs.acme.test/1"])
    assert result.exit_code == 0
    assert "Already added" in result.output
