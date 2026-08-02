"""Tests for the pure doctor logic in :mod:`atlas.cli.doctor`."""

from __future__ import annotations

import pytest

from atlas.ai.cli import RunResult
from atlas.cli.doctor import BackendStatus, DoctorReport, render_report, run_doctor
from atlas.config import AiConfig, SecretStore
from tests.conftest import FakeKeyring, FakeSubprocessRunner


def _store(fake_keyring: FakeKeyring) -> SecretStore:
    return SecretStore(fake_keyring)


def _runner(available: bool) -> FakeSubprocessRunner:
    # ``ClaudeCodeAdapter.is_available()`` runs ``claude --version``; a zero exit
    # means available. A missing binary is modelled by raising FileNotFoundError.
    code = 0 if available else 1
    return FakeSubprocessRunner(RunResult(returncode=code, stdout="v1", stderr=""))


def test_run_doctor_default_config_backends_and_order(fake_keyring: FakeKeyring) -> None:
    # Default config: claude_code (default) + openrouter (failover). The fake
    # runner makes claude_code available; openrouter has no key -> unavailable.
    report = run_doctor(AiConfig(), _store(fake_keyring), runner=_runner(available=True))

    assert [b.name for b in report.backends] == ["claude_code", "openrouter"]
    assert [b.role for b in report.backends] == ["default", "failover"]
    assert report.backends[0].available is True
    assert report.backends[1].available is False
    assert report.healthy is True


def test_run_doctor_claude_unavailable_when_binary_missing(fake_keyring: FakeKeyring) -> None:
    runner = FakeSubprocessRunner(raises=FileNotFoundError("claude"))
    report = run_doctor(AiConfig(), _store(fake_keyring), runner=runner)
    assert report.backends[0].available is False
    assert "unavailable" in report.backends[0].detail


def test_run_doctor_openrouter_available_with_key(fake_keyring: FakeKeyring) -> None:
    store = _store(fake_keyring)
    store.set("openrouter", "or-key")
    config = AiConfig.model_validate({"default_backend": "openrouter", "failover": []})

    report = run_doctor(config, store, runner=_runner(available=False))

    assert report.backends[0].name == "openrouter"
    assert report.backends[0].available is True
    assert report.healthy is True


def test_run_doctor_unknown_backend_recorded_not_raised(fake_keyring: FakeKeyring) -> None:
    config = AiConfig.model_validate({"default_backend": "nope", "failover": []})
    report = run_doctor(config, _store(fake_keyring), runner=_runner(available=True))
    status = report.backends[0]
    assert status.available is False
    assert "not configured" in status.detail
    assert report.healthy is False


def test_run_doctor_bare_claude_without_key_recorded(
    fake_keyring: FakeKeyring,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Bare mode with no resolvable key raises LLMAuthError at construction; doctor
    # must record it as a config problem rather than propagating.
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    config = AiConfig.model_validate(
        {
            "default_backend": "claude_code",
            "failover": [],
            "backends": {"claude_code": {"use_bare": True}},
        }
    )
    report = run_doctor(config, _store(fake_keyring), runner=_runner(available=True))
    assert report.backends[0].available is False
    assert "not configured" in report.backends[0].detail


def test_run_doctor_all_unavailable_is_unhealthy(fake_keyring: FakeKeyring) -> None:
    report = run_doctor(AiConfig(), _store(fake_keyring), runner=_runner(available=False))
    assert all(not b.available for b in report.backends)
    assert report.healthy is False


def test_render_report_text_marks_and_summary() -> None:
    report = DoctorReport(
        backends=[
            BackendStatus(name="claude_code", role="default", available=True, detail="available"),
            BackendStatus(name="openrouter", role="failover", available=False, detail="no key"),
        ],
        healthy=True,
    )
    text = render_report(report)
    assert "OK  claude_code (default) — available" in text
    assert "XX  openrouter (failover) — no key" in text
    assert "Overall: healthy." in text


def test_render_report_unhealthy_summary() -> None:
    report = DoctorReport(backends=[], healthy=False)
    assert "Overall: no usable backend." in render_report(report)


def test_report_json_round_trips() -> None:
    # The command layer emits report.model_dump_json(); ensure it round-trips.
    report = DoctorReport(
        backends=[BackendStatus(name="x", role="default", available=True, detail="ok")],
        healthy=True,
    )
    assert DoctorReport.model_validate_json(report.model_dump_json()) == report
