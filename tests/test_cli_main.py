"""Tests for the Typer app and ``atlas doctor`` command in :mod:`atlas.cli.main`."""

from __future__ import annotations

import json

import pytest
from typer.testing import CliRunner

import atlas.cli.main as app_module
from atlas.cli.doctor import BackendStatus, DoctorReport
from atlas.cli.main import app
from atlas.config import Config, SecretStore
from atlas.config.errors import KeyringUnavailableError
from tests.conftest import FakeKeyring

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


@pytest.fixture(autouse=True)
def stub_setup_logging(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, object]]:
    """Stub the callback's logging setup so no test writes a real log file.

    Records each call's kwargs so tests can assert the resolved options; returns
    the recording list.
    """
    calls: list[dict[str, object]] = []

    def _fake(**kwargs: object) -> int:
        calls.append(kwargs)
        return 0

    monkeypatch.setattr(app_module, "setup_logging", _fake)
    return calls


@pytest.fixture
def stub_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Stub config + secret store so the command touches no real config/keyring.

    The store is a real :class:`SecretStore` over an in-memory keyring so
    ``build_aggregator_health`` (which reads credential handles) works offline.
    """
    monkeypatch.setattr(app_module, "load_config", lambda: Config())
    monkeypatch.setattr(app_module, "default_secret_store", lambda: SecretStore(FakeKeyring()))


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
    monkeypatch.setattr(
        app_module, "run_doctor", lambda config, store, **kwargs: _report(healthy=True)
    )
    result = runner.invoke(app, ["doctor"])
    assert result.exit_code == 0
    assert "AI backends" in result.output
    assert "claude_code" in result.output
    assert "At least one backend is usable" in result.output


def test_doctor_unhealthy_exits_one(
    stub_env: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        app_module, "run_doctor", lambda config, store, **kwargs: _report(healthy=False)
    )
    result = runner.invoke(app, ["doctor"])
    assert result.exit_code == 1
    assert "No usable backend configured" in result.output


def test_doctor_json_output(
    stub_env: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        app_module, "run_doctor", lambda config, store, **kwargs: _report(healthy=True)
    )
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


def _capture_kwargs(monkeypatch: pytest.MonkeyPatch, captured: dict[str, object]) -> None:
    def _run(config: object, store: object, **kwargs: object) -> DoctorReport:
        captured.update(kwargs)
        return _report(healthy=True)

    monkeypatch.setattr(app_module, "run_doctor", _run)


def test_doctor_default_does_not_probe(
    stub_env: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}
    _capture_kwargs(monkeypatch, captured)
    runner.invoke(app, ["doctor"])
    assert captured == {"probe": False, "refresh": False}


def test_doctor_probe_flag_enables_probe(
    stub_env: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}
    _capture_kwargs(monkeypatch, captured)
    runner.invoke(app, ["doctor", "--probe"])
    assert captured == {"probe": True, "refresh": False}


def test_doctor_refresh_implies_probe(
    stub_env: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}
    _capture_kwargs(monkeypatch, captured)
    runner.invoke(app, ["doctor", "--refresh"])
    assert captured == {"probe": True, "refresh": True}


def test_callback_initializes_logging_from_config(
    stub_env: None,
    stub_setup_logging: list[dict[str, object]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A default config drives setup_logging with the [logging] section values.
    monkeypatch.setattr(
        app_module, "run_doctor", lambda config, store, **kwargs: _report(healthy=True)
    )
    runner.invoke(app, ["doctor"])
    assert stub_setup_logging == [
        {
            "log_level": None,
            "verbose": 0,
            "config_level": "WARNING",
            "file_enabled": True,
            "max_bytes": 1_000_000,
            "backup_count": 3,
        }
    ]


def test_callback_passes_verbose_and_log_level(
    stub_env: None,
    stub_setup_logging: list[dict[str, object]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        app_module, "run_doctor", lambda config, store, **kwargs: _report(healthy=True)
    )
    runner.invoke(app, ["-v", "--log-level", "DEBUG", "doctor"])
    assert stub_setup_logging[0]["verbose"] == 1
    assert stub_setup_logging[0]["log_level"] == "DEBUG"


def test_callback_tolerates_bad_config(
    stub_setup_logging: list[dict[str, object]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A config that fails to load must not break logging setup; the callback
    # falls back to CLI-only options and the command still reports the error.
    def _boom() -> Config:
        raise KeyringUnavailableError("no secure keychain")

    monkeypatch.setattr(app_module, "load_config", _boom)
    result = runner.invoke(app, ["-v", "doctor"])
    assert result.exit_code == 1
    # setup_logging was called with the CLI options only (no config_level).
    assert stub_setup_logging == [{"log_level": None, "verbose": 1}]
