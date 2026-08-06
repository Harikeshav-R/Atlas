"""Tests for the pure quiet-hours / daily-cap gating in :mod:`atlas.notify.window`."""

from __future__ import annotations

from datetime import UTC, datetime, time

import pytest

from atlas.notify.window import day_key, in_quiet_hours, parse_quiet_hours


def _at(hour: int, minute: int = 0) -> datetime:
    """A timezone-aware UTC datetime at ``hour:minute`` on a fixed date."""
    return datetime(2026, 8, 6, hour, minute, tzinfo=UTC)


def test_parse_quiet_hours_valid_window() -> None:
    assert parse_quiet_hours("22:00-08:00") == (time(22, 0), time(8, 0))


@pytest.mark.parametrize(
    "spec",
    [
        "",  # empty
        "   ",  # whitespace only
        "22:00",  # no separator
        "9pm-8am",  # non-numeric
        "22:00-",  # missing end
    ],
)
def test_parse_quiet_hours_malformed_is_none(spec: str) -> None:
    # A bad window disables quiet hours rather than crashing the daemon.
    assert parse_quiet_hours(spec) is None


def test_in_quiet_hours_empty_spec_is_never_quiet() -> None:
    assert in_quiet_hours(_at(3), "") is False


def test_in_quiet_hours_malformed_spec_is_never_quiet() -> None:
    assert in_quiet_hours(_at(3), "nonsense") is False


@pytest.mark.parametrize(
    ("hour", "expected"),
    [
        (8, False),  # before the window
        (9, True),  # at start (inclusive)
        (11, True),  # inside
        (12, False),  # at end (exclusive)
        (14, False),  # after the window
    ],
)
def test_in_quiet_hours_non_wrapping_window(hour: int, expected: bool) -> None:
    # A same-day window: 09:00-12:00.
    assert in_quiet_hours(_at(hour), "09:00-12:00") is expected


@pytest.mark.parametrize(
    ("hour", "expected"),
    [
        (23, True),  # after start (evening arm)
        (2, True),  # after midnight, before end (morning arm)
        (8, False),  # at end (exclusive)
        (12, False),  # midday, outside both arms
        (22, True),  # at start (inclusive)
    ],
)
def test_in_quiet_hours_wrapping_window(hour: int, expected: bool) -> None:
    # A window that wraps past midnight: 22:00-08:00.
    assert in_quiet_hours(_at(hour), "22:00-08:00") is expected


def test_day_key_is_the_calendar_day() -> None:
    assert day_key(_at(23, 59)) == "2026-08-06"
