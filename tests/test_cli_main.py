"""Tests for the Typer app and ``atlas doctor`` command in :mod:`atlas.cli.main`."""

from __future__ import annotations

import json

import pytest
from typer.testing import CliRunner

import atlas.cli.main as app_module
from atlas.cli.doctor import BackendStatus, DoctorReport
from atlas.cli.main import app
from atlas.config import Config
from atlas.config.errors import KeyringUnavailableError

runner = CliRunner()


def _report(*, healthy: bool) -> DoctorReport:
    return DoctorReport(
        backends=[
            BackendStatus(
                name="claude_code",
                role="default",
                available=healthy,
                detail="available" if healthy else "unavailable",
            )
        ],
        healthy=healthy,
    )


@pytest.fixture
def stub_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Stub config + secret store so the command touches no real config/keyring."""
    monkeypatch.setattr(app_module, "load_config", lambda: Config())
    monkeypatch.setattr(app_module, "default_secret_store", lambda: object())


def test_no_args_shows_help_and_exits_nonzero() -> None:
    # A bare `atlas` invocation is help (no_args_is_help), exit code 2.
    result = runner.invoke(app, [])
    assert result.exit_code == 2
    assert "Usage:" in result.output


def test_help_lists_doctor() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "doctor" in result.output


def test_doctor_text_healthy_exit_zero(
    stub_env: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(app_module, "run_doctor", lambda config, store: _report(healthy=True))
    result = runner.invoke(app, ["doctor"])
    assert result.exit_code == 0
    assert "AI backends" in result.output
    assert "claude_code" in result.output
    assert "At least one backend is usable" in result.output


def test_doctor_unhealthy_exits_one(
    stub_env: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(app_module, "run_doctor", lambda config, store: _report(healthy=False))
    result = runner.invoke(app, ["doctor"])
    assert result.exit_code == 1
    assert "No usable backend configured" in result.output


def test_doctor_json_output(
    stub_env: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(app_module, "run_doctor", lambda config, store: _report(healthy=True))
    result = runner.invoke(app, ["doctor", "--json"])
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["healthy"] is True
    assert payload["backends"][0]["name"] == "claude_code"


def test_doctor_reports_config_error_and_exits_one(monkeypatch: pytest.MonkeyPatch) -> None:
    def _boom() -> Config:
        raise KeyringUnavailableError("no secure keychain")

    monkeypatch.setattr(app_module, "load_config", _boom)
    result = runner.invoke(app, ["doctor"])
    assert result.exit_code == 1
    assert "atlas doctor:" in result.output
    assert "no secure keychain" in result.output
