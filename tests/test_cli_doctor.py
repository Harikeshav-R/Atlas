"""Tests for the pure doctor logic in :mod:`atlas.cli.doctor`."""

from __future__ import annotations

from collections.abc import Callable

import pytest

from atlas.ai.base import LLMProvider
from atlas.ai.cli import RunResult
from atlas.ai.probe import BackendCapabilities, ProbeResult
from atlas.cli.doctor import (
    AggregatorHealth,
    BackendStatus,
    DoctorReport,
    build_aggregator_health,
    render_report,
    run_doctor,
)
from atlas.config import AiConfig, SecretStore
from atlas.config.schema import AggregatorsConfig
from tests.conftest import FakeKeyring, FakeSubprocessRunner


def _empty_cache() -> dict[str, ProbeResult]:
    return {}


def _noop_save(results: object) -> None:
    return None


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
    report = run_doctor(
        AiConfig(), _store(fake_keyring), runner=_runner(available=True), cache_load=_empty_cache
    )

    assert [b.name for b in report.backends] == ["claude_code", "openrouter"]
    assert [b.role for b in report.backends] == ["default", "failover"]
    assert report.backends[0].available is True
    assert report.backends[1].available is False
    assert report.healthy is True


def test_run_doctor_claude_unavailable_when_binary_missing(fake_keyring: FakeKeyring) -> None:
    runner = FakeSubprocessRunner(raises=FileNotFoundError("claude"))
    report = run_doctor(AiConfig(), _store(fake_keyring), runner=runner, cache_load=_empty_cache)
    assert report.backends[0].available is False
    assert "binary not found" in report.backends[0].detail


def test_run_doctor_claude_too_old_reports_version_reason(fake_keyring: FakeKeyring) -> None:
    # A CLI older than the floor is unavailable with a version-specific reason.
    runner = FakeSubprocessRunner(RunResult(returncode=0, stdout="1.0.0 (Claude Code)", stderr=""))
    config = AiConfig.model_validate({"default_backend": "claude_code", "failover": []})
    report = run_doctor(config, _store(fake_keyring), runner=runner, cache_load=_empty_cache)
    assert report.backends[0].available is False
    assert "too old" in report.backends[0].detail


def test_run_doctor_openrouter_available_with_key(fake_keyring: FakeKeyring) -> None:
    store = _store(fake_keyring)
    store.set("openrouter", "or-key")
    config = AiConfig.model_validate({"default_backend": "openrouter", "failover": []})

    report = run_doctor(config, store, runner=_runner(available=False), cache_load=_empty_cache)

    assert report.backends[0].name == "openrouter"
    assert report.backends[0].available is True
    assert report.healthy is True


def test_run_doctor_unknown_backend_recorded_not_raised(fake_keyring: FakeKeyring) -> None:
    config = AiConfig.model_validate({"default_backend": "nope", "failover": []})
    report = run_doctor(
        config, _store(fake_keyring), runner=_runner(available=True), cache_load=_empty_cache
    )
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
    report = run_doctor(
        config, _store(fake_keyring), runner=_runner(available=True), cache_load=_empty_cache
    )
    assert report.backends[0].available is False
    assert "not configured" in report.backends[0].detail


def test_run_doctor_all_unavailable_is_unhealthy(fake_keyring: FakeKeyring) -> None:
    report = run_doctor(
        AiConfig(), _store(fake_keyring), runner=_runner(available=False), cache_load=_empty_cache
    )
    assert all(not b.available for b in report.backends)
    assert report.healthy is False


# --- capability probing (opt-in) ------------------------------------------------


def _caps(**flags: bool) -> BackendCapabilities:
    return BackendCapabilities(**flags)


def _fake_probe(caps: BackendCapabilities) -> Callable[[LLMProvider], ProbeResult]:
    # A probe_fn that ignores the provider and returns a fixed result per backend.
    def _probe(provider: LLMProvider) -> ProbeResult:
        return ProbeResult(
            backend=provider.name,
            ok=True,
            capabilities=caps,
            detail="probe succeeded",
        )

    return _probe


def test_probe_false_attaches_cached_capabilities(fake_keyring: FakeKeyring) -> None:
    cached = {
        "claude_code": ProbeResult(
            backend="claude_code",
            ok=True,
            capabilities=_caps(json_output=True, json_schema=True),
            detail="probe succeeded",
        )
    }
    config = AiConfig.model_validate({"default_backend": "claude_code", "failover": []})
    report = run_doctor(
        config,
        _store(fake_keyring),
        runner=_runner(available=True),
        cache_load=lambda: dict(cached),
    )
    status = report.backends[0]
    assert status.capabilities is not None
    assert status.capabilities.json_schema is True
    assert status.capabilities_cached is True


def test_probe_false_no_cache_leaves_capabilities_none(fake_keyring: FakeKeyring) -> None:
    config = AiConfig.model_validate({"default_backend": "claude_code", "failover": []})
    report = run_doctor(
        config, _store(fake_keyring), runner=_runner(available=True), cache_load=_empty_cache
    )
    assert report.backends[0].capabilities is None
    assert report.backends[0].capabilities_cached is False


def test_probe_true_runs_probe_and_saves(fake_keyring: FakeKeyring) -> None:
    saved: dict[str, ProbeResult] = {}
    config = AiConfig.model_validate({"default_backend": "claude_code", "failover": []})
    report = run_doctor(
        config,
        _store(fake_keyring),
        runner=_runner(available=True),
        probe=True,
        probe_fn=_fake_probe(_caps(json_output=True, streaming=True)),
        cache_load=_empty_cache,
        cache_save=lambda results: saved.update(results),
    )
    status = report.backends[0]
    assert status.capabilities is not None
    assert status.capabilities.streaming is True
    assert status.capabilities_cached is False
    # The fresh result was persisted.
    assert "claude_code" in saved


def test_probe_true_reuses_cache_without_refresh(fake_keyring: FakeKeyring) -> None:
    probed: list[str] = []

    def _probe(provider: LLMProvider) -> ProbeResult:
        probed.append(provider.name)
        return ProbeResult(
            backend=provider.name,
            ok=True,
            capabilities=_caps(json_output=True),
            detail="probe succeeded",
        )

    cached = {
        "claude_code": ProbeResult(
            backend="claude_code",
            ok=True,
            capabilities=_caps(json_schema=True),
            detail="probe succeeded",
        )
    }
    config = AiConfig.model_validate({"default_backend": "claude_code", "failover": []})
    report = run_doctor(
        config,
        _store(fake_keyring),
        runner=_runner(available=True),
        probe=True,
        probe_fn=_probe,
        cache_load=lambda: dict(cached),
        cache_save=_noop_save,
    )
    # Cached result reused (schema True from cache), live probe never called.
    assert probed == []
    assert report.backends[0].capabilities is not None
    assert report.backends[0].capabilities.json_schema is True
    assert report.backends[0].capabilities_cached is True


def test_refresh_reprobes_ignoring_cache(fake_keyring: FakeKeyring) -> None:
    probed: list[str] = []

    def _probe(provider: LLMProvider) -> ProbeResult:
        probed.append(provider.name)
        return ProbeResult(
            backend=provider.name,
            ok=True,
            capabilities=_caps(json_output=True),
            detail="probe succeeded",
        )

    cached = {
        "claude_code": ProbeResult(
            backend="claude_code",
            ok=True,
            capabilities=_caps(json_schema=True),
            detail="probe succeeded",
        )
    }
    config = AiConfig.model_validate({"default_backend": "claude_code", "failover": []})
    report = run_doctor(
        config,
        _store(fake_keyring),
        runner=_runner(available=True),
        probe=True,
        refresh=True,
        probe_fn=_probe,
        cache_load=lambda: dict(cached),
        cache_save=_noop_save,
    )
    # Refresh forces a live probe even though a cache entry existed.
    assert probed == ["claude_code"]
    assert report.backends[0].capabilities_cached is False
    assert report.backends[0].capabilities is not None
    assert report.backends[0].capabilities.json_output is True


def _rendered(report: DoctorReport) -> str:
    # render_report returns a Rich renderable that uses the shared Atlas theme's
    # semantic styles; capture it through that same console so those styles resolve.
    from atlas.cli.console import console

    with console.capture() as capture:
        console.print(render_report(report))
    return capture.get()


def test_render_report_shows_backends_and_healthy_summary() -> None:
    report = DoctorReport(
        backends=[
            BackendStatus(name="claude_code", role="default", available=True, detail="available"),
            BackendStatus(name="openrouter", role="failover", available=False, detail="no key"),
        ],
        healthy=True,
    )
    text = _rendered(report)
    assert "AI backends" in text
    assert "claude_code" in text
    assert "openrouter" in text
    assert "no key" in text
    assert "At least one backend is usable" in text


def test_render_report_unhealthy_summary() -> None:
    report = DoctorReport(backends=[], healthy=False)
    assert "No usable backend configured" in _rendered(report)


def test_render_report_shows_capability_glyphs_and_labels() -> None:
    report = DoctorReport(
        backends=[
            BackendStatus(
                name="claude_code",
                role="default",
                available=True,
                detail="available",
                capabilities=BackendCapabilities(json_output=True, json_schema=False),
                capabilities_cached=True,
            )
        ],
        healthy=True,
    )
    text = _rendered(report)
    # Capability labels and the cached tag appear.
    assert "json" in text
    assert "schema" in text
    assert "model" in text
    assert "(cached)" in text


def test_render_report_not_probed_when_no_capabilities() -> None:
    report = DoctorReport(
        backends=[BackendStatus(name="claude_code", role="default", available=True, detail="ok")],
        healthy=True,
    )
    assert "not probed" in _rendered(report)


def test_render_report_live_capabilities_have_no_cached_tag() -> None:
    report = DoctorReport(
        backends=[
            BackendStatus(
                name="claude_code",
                role="default",
                available=True,
                detail="available",
                capabilities=BackendCapabilities(json_output=True),
                capabilities_cached=False,
            )
        ],
        healthy=True,
    )
    text = _rendered(report)
    assert "json" in text
    assert "(cached)" not in text


def test_report_json_round_trips() -> None:
    # The command layer emits report.model_dump_json(); ensure it round-trips.
    report = DoctorReport(
        backends=[BackendStatus(name="x", role="default", available=True, detail="ok")],
        healthy=True,
        aggregators=[
            AggregatorHealth(name="adzuna", requires_key=True, active=False, detail="needs API key")
        ],
    )
    assert DoctorReport.model_validate_json(report.model_dump_json()) == report


# --- aggregator health ----------------------------------------------------------


def test_build_aggregator_health_free_and_disabled_and_needs_key(fake_keyring: FakeKeyring) -> None:
    store = _store(fake_keyring)
    # Default config: free feeds active; key-gated ones disabled.
    health = {h.name: h for h in build_aggregator_health(AggregatorsConfig(), store)}
    assert set(health) == {"adzuna", "remoteok", "remotive", "usajobs"}
    assert health["remoteok"].active is True
    assert health["remoteok"].detail == "active"
    assert health["remoteok"].requires_key is False
    # Disabled key-gated provider.
    assert health["adzuna"].active is False
    assert health["adzuna"].detail == "disabled"
    # Enabled but keyless → needs API key.
    config = AggregatorsConfig.model_validate({"adzuna": {"enabled": True}})
    needs = {h.name: h for h in build_aggregator_health(config, store)}
    assert needs["adzuna"].detail == "needs API key"
    assert needs["adzuna"].active is False


def test_build_aggregator_health_active_when_keyed(fake_keyring: FakeKeyring) -> None:
    store = _store(fake_keyring)
    store.set("adzuna_app_id", "id")
    store.set("adzuna_app_key", "key")
    config = AggregatorsConfig.model_validate({"adzuna": {"enabled": True}})
    health = {h.name: h for h in build_aggregator_health(config, store)}
    assert health["adzuna"].active is True
    assert health["adzuna"].detail == "active"


def test_render_report_shows_aggregators() -> None:
    report = DoctorReport(
        backends=[BackendStatus(name="claude_code", role="default", available=True, detail="ok")],
        healthy=True,
        aggregators=[
            AggregatorHealth(name="remoteok", requires_key=False, active=True, detail="active"),
            AggregatorHealth(
                name="adzuna", requires_key=True, active=False, detail="needs API key"
            ),
        ],
    )
    text = _rendered(report)
    assert "Aggregator sources" in text
    assert "remoteok" in text
    assert "adzuna" in text
    assert "needs API key" in text
    assert "free" in text
    assert "required" in text


def test_render_report_omits_aggregator_table_when_empty() -> None:
    report = DoctorReport(
        backends=[BackendStatus(name="claude_code", role="default", available=True, detail="ok")],
        healthy=True,
    )
    assert "Aggregator sources" not in _rendered(report)
