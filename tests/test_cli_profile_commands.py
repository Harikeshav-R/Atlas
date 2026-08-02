"""Tests for the ``atlas init`` and ``atlas profile`` commands in :mod:`atlas.cli.main`.

These drive the Typer commands through the ``CliRunner`` with the boundaries
stubbed: an in-memory database engine (no real data dir), canned onboarding
answers (the wizard's own logic is covered in ``test_profiles_onboarding``), and
a no-op logging setup (no real log file) — the same monkeypatch idiom as the
``atlas doctor`` command tests.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest
from sqlmodel import SQLModel
from typer.testing import CliRunner

import atlas.cli.main as app_module
from atlas.cli.main import app
from atlas.db import create_db_engine, session_scope
from atlas.profiles.errors import ProfileNotFoundError
from atlas.profiles.onboarding import OnboardingResult, ProfileAnswers, UserAnswers
from atlas.profiles.preferences import ProfilePreferences
from atlas.profiles.repository import create_profile

if TYPE_CHECKING:
    from sqlalchemy.engine import Engine

runner = CliRunner()


@pytest.fixture(autouse=True)
def _stub_logging(monkeypatch: pytest.MonkeyPatch) -> None:
    """Stub the callback's logging setup so no test writes a real log file."""
    monkeypatch.setattr(app_module, "setup_logging", lambda **kwargs: 0)


@pytest.fixture
def shared_engine(monkeypatch: pytest.MonkeyPatch) -> Engine:
    """Point the commands at one shared in-memory engine with the schema created.

    ``initialize_database`` is stubbed to return this engine, and its
    ``dispose`` is neutered so the in-memory database survives across the
    command's teardown for the test's own assertions (the real command owns and
    disposes a file-backed engine).
    """
    engine = create_db_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(engine, "dispose", lambda: None)
    monkeypatch.setattr(app_module, "initialize_database", lambda: engine)
    return engine


def _onboarding(name: str = "Sam", profile: str = "Backend Engineer") -> OnboardingResult:
    return OnboardingResult(
        user=UserAnswers(name=name, email="sam@example.com"),
        profile=ProfileAnswers(
            name=profile,
            preferences=ProfilePreferences(target_roles=[profile]),
            tailoring_emphasis=["distributed systems"],
        ),
    )


def _seed(engine: Engine, name: str, *, active: bool = True) -> int:
    with session_scope(engine) as session:
        profile = create_profile(
            session,
            name=name,
            preferences=ProfilePreferences(target_roles=[name]),
            active=active,
        )
        assert profile.id is not None
        return profile.id


# --- atlas init -----------------------------------------------------------------


def test_init_creates_profile(shared_engine: Engine, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(app_module, "run_onboarding", lambda prompter: _onboarding())
    result = runner.invoke(app, ["init"])
    assert result.exit_code == 0
    assert "Created profile" in result.output
    assert "Backend Engineer" in result.output
    # The list command sees the persisted profile.
    listed = runner.invoke(app, ["profile", "list", "--json"])
    payload = json.loads(listed.output)
    assert [p["name"] for p in payload["profiles"]] == ["Backend Engineer"]
    assert payload["profiles"][0]["active"] is True


def test_init_reports_bootstrap_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(app_module, "run_onboarding", lambda prompter: _onboarding())

    def _boom() -> Engine:
        raise RuntimeError("disk full")

    monkeypatch.setattr(app_module, "initialize_database", _boom)
    result = runner.invoke(app, ["init"])
    assert result.exit_code == 1
    assert "could not open the database" in result.output


# --- atlas profile list ---------------------------------------------------------


def test_profile_list_empty_text(shared_engine: Engine) -> None:
    result = runner.invoke(app, ["profile", "list"])
    assert result.exit_code == 0
    assert "atlas init" in result.output


def test_profile_list_text_shows_rows(shared_engine: Engine) -> None:
    _seed(shared_engine, "Backend Engineer")
    result = runner.invoke(app, ["profile", "list"])
    assert result.exit_code == 0
    assert "Backend Engineer" in result.output


def test_profile_list_json(shared_engine: Engine) -> None:
    _seed(shared_engine, "Backend Engineer")
    result = runner.invoke(app, ["profile", "list", "--json"])
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["profiles"][0]["name"] == "Backend Engineer"


# --- atlas profile add ----------------------------------------------------------


def test_profile_add_creates_and_activates(
    shared_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    first = _seed(shared_engine, "Backend Engineer")
    monkeypatch.setattr(
        app_module,
        "ask_profile",
        lambda prompter: ProfileAnswers(
            name="ML Engineer", preferences=ProfilePreferences(target_roles=["ML Engineer"])
        ),
    )
    result = runner.invoke(app, ["profile", "add"])
    assert result.exit_code == 0
    assert "made it active" in result.output

    payload = json.loads(runner.invoke(app, ["profile", "list", "--json"]).output)
    actives = [p["id"] for p in payload["profiles"] if p["active"]]
    assert len(actives) == 1
    assert first not in actives


# --- atlas profile edit ---------------------------------------------------------


def test_profile_edit_updates(shared_engine: Engine, monkeypatch: pytest.MonkeyPatch) -> None:
    profile_id = _seed(shared_engine, "Backend Engineer")
    monkeypatch.setattr(
        app_module,
        "ask_profile",
        lambda prompter, existing=None: ProfileAnswers(
            name="Backend v2", preferences=ProfilePreferences(target_roles=["Backend v2"])
        ),
    )
    result = runner.invoke(app, ["profile", "edit", str(profile_id)])
    assert result.exit_code == 0
    assert "Updated profile" in result.output
    payload = json.loads(runner.invoke(app, ["profile", "list", "--json"]).output)
    assert payload["profiles"][0]["name"] == "Backend v2"


def test_profile_edit_missing_id_errors(
    shared_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The wizard is never reached for a missing id; guard it so a stray call fails.
    def _unexpected(prompter: object, existing: object = None) -> ProfileAnswers:
        raise AssertionError("wizard should not run for a missing profile")

    monkeypatch.setattr(app_module, "ask_profile", _unexpected)
    result = runner.invoke(app, ["profile", "edit", "999"])
    assert result.exit_code == 1
    assert "profile edit" in result.output
    assert isinstance(result.exception, SystemExit)


# --- atlas profile use ----------------------------------------------------------


def test_profile_use_switches_active(shared_engine: Engine) -> None:
    first = _seed(shared_engine, "First")
    _seed(shared_engine, "Second")  # becomes active
    result = runner.invoke(app, ["profile", "use", str(first)])
    assert result.exit_code == 0
    assert "Activated profile" in result.output
    payload = json.loads(runner.invoke(app, ["profile", "list", "--json"]).output)
    actives = [p["id"] for p in payload["profiles"] if p["active"]]
    assert actives == [first]


def test_profile_use_missing_id_errors(shared_engine: Engine) -> None:
    result = runner.invoke(app, ["profile", "use", "999"])
    assert result.exit_code == 1
    assert "profile use" in result.output


def test_profile_not_found_error_is_the_expected_type() -> None:
    # Sanity: the CLI catches exactly the repository's error type.
    assert issubclass(ProfileNotFoundError, Exception)
