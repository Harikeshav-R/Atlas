"""Tests for the custom column types in :mod:`atlas.db.types`."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

from atlas.db.types import UtcDateTime


def test_bind_param_converts_aware_value_to_naive_utc() -> None:
    kolkata = timezone(timedelta(hours=5, minutes=30))
    value = datetime(2026, 8, 3, 17, 30, tzinfo=kolkata)  # 12:00 UTC
    stored = UtcDateTime().process_bind_param(value, dialect=None)  # type: ignore[arg-type]
    assert stored == datetime(2026, 8, 3, 12, 0)
    assert stored is not None
    assert stored.tzinfo is None


def test_bind_param_assumes_naive_value_is_utc() -> None:
    value = datetime(2026, 8, 3, 12, 0)
    stored = UtcDateTime().process_bind_param(value, dialect=None)  # type: ignore[arg-type]
    assert stored == value


def test_result_value_reattaches_utc() -> None:
    stored = datetime(2026, 8, 3, 12, 0)
    loaded = UtcDateTime().process_result_value(stored, dialect=None)  # type: ignore[arg-type]
    assert loaded == datetime(2026, 8, 3, 12, 0, tzinfo=UTC)
    assert loaded is not None
    assert loaded.tzinfo is UTC


def test_none_passes_through_both_directions() -> None:
    kind = UtcDateTime()
    assert kind.process_bind_param(None, dialect=None) is None  # type: ignore[arg-type]
    assert kind.process_result_value(None, dialect=None) is None  # type: ignore[arg-type]
