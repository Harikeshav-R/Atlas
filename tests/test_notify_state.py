"""Tests for the notification run-state in :mod:`atlas.notify.state`."""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from atlas.notify.state import NotifyState, load_notify_state, save_notify_state


def test_notify_state_file_lives_in_state_dir() -> None:
    from atlas.config.paths import notify_state_file

    path = notify_state_file()
    assert path.name == "notify-state.json"
    assert "atlas" in str(path).lower()


def test_defaults() -> None:
    state = NotifyState()
    assert state.last_notified_score_id == 0
    assert state.day == ""
    assert state.daily_count == 0
    assert state.notified_deadline_keys == []


def test_save_then_load_round_trips(tmp_path: Path) -> None:
    target = tmp_path / "notify-state.json"
    state = NotifyState(
        last_notified_score_id=42,
        day="2026-08-06",
        daily_count=3,
        notified_deadline_keys=["7:2026-08-07T09:00:00+00:00"],
    )
    save_notify_state(state, target)
    assert load_notify_state(target) == state


def test_save_creates_missing_parent_dir(tmp_path: Path) -> None:
    target = tmp_path / "nested" / "dir" / "notify-state.json"
    save_notify_state(NotifyState(last_notified_score_id=1), target)
    assert target.exists()


def test_load_missing_file_returns_default(tmp_path: Path) -> None:
    assert load_notify_state(tmp_path / "does-not-exist.json") == NotifyState()


def test_load_corrupt_json_returns_default(tmp_path: Path) -> None:
    target = tmp_path / "notify-state.json"
    target.write_text("{ not valid json", encoding="utf-8")
    assert load_notify_state(target) == NotifyState()


def test_load_wrong_shape_returns_default(tmp_path: Path) -> None:
    # Valid JSON but the wrong type for a field → validation fails → fresh default.
    target = tmp_path / "notify-state.json"
    target.write_text('{"last_notified_score_id": "not-an-int"}', encoding="utf-8")
    assert load_notify_state(target) == NotifyState()


def test_load_corrupt_state_logs_warning(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    target = tmp_path / "notify-state.json"
    target.write_text("{ not valid json", encoding="utf-8")
    with caplog.at_level(logging.WARNING, logger="atlas.notify.state"):
        assert load_notify_state(target) == NotifyState()
    assert any(
        record.levelno == logging.WARNING and "unreadable notification state" in record.message
        for record in caplog.records
    )
