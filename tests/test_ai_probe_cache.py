"""Tests for the probe-result cache in :mod:`atlas.ai.probe_cache`."""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from atlas.ai.probe import BackendCapabilities, ProbeResult
from atlas.ai.probe_cache import load_probe_cache, probe_cache_file, save_probe_cache


def _result(backend: str, *, ok: bool = True) -> ProbeResult:
    return ProbeResult(
        backend=backend,
        ok=ok,
        capabilities=BackendCapabilities(json_output=ok, json_schema=ok),
        detail="probe succeeded" if ok else "probe failed",
    )


def test_probe_cache_file_lives_in_cache_dir() -> None:
    path = probe_cache_file()
    assert path.name == "capabilities.json"
    # It sits under the platformdirs cache dir (parent is the atlas cache dir).
    assert "atlas" in str(path).lower()


def test_save_then_load_round_trips(tmp_path: Path) -> None:
    target = tmp_path / "capabilities.json"
    results = {"claude_code": _result("claude_code"), "openrouter": _result("openrouter", ok=False)}
    save_probe_cache(results, target)
    loaded = load_probe_cache(target)
    assert loaded == results


def test_save_creates_missing_parent_dir(tmp_path: Path) -> None:
    target = tmp_path / "nested" / "dir" / "capabilities.json"
    save_probe_cache({"claude_code": _result("claude_code")}, target)
    assert target.exists()


def test_load_missing_file_returns_empty(tmp_path: Path) -> None:
    assert load_probe_cache(tmp_path / "does-not-exist.json") == {}


def test_load_corrupt_json_returns_empty(tmp_path: Path) -> None:
    target = tmp_path / "capabilities.json"
    target.write_text("{ this is not valid json", encoding="utf-8")
    assert load_probe_cache(target) == {}


def test_load_wrong_shape_returns_empty(tmp_path: Path) -> None:
    # Valid JSON, but not a ProbeResult mapping → treated as empty, no raise.
    target = tmp_path / "capabilities.json"
    target.write_text('{"claude_code": {"unexpected": "shape"}}', encoding="utf-8")
    assert load_probe_cache(target) == {}


def test_load_non_object_json_returns_empty(tmp_path: Path) -> None:
    # Top-level JSON array has no .items() → AttributeError path, still empty.
    target = tmp_path / "capabilities.json"
    target.write_text("[1, 2, 3]", encoding="utf-8")
    assert load_probe_cache(target) == {}


def test_load_corrupt_cache_logs_warning(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    target = tmp_path / "capabilities.json"
    target.write_text("{ not valid json", encoding="utf-8")
    with caplog.at_level(logging.WARNING, logger="atlas.ai.probe_cache"):
        assert load_probe_cache(target) == {}
    assert any(
        record.levelno == logging.WARNING and "unreadable probe cache" in record.message
        for record in caplog.records
    )
