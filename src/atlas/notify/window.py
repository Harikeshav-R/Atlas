"""Pure quiet-hours and daily-cap gating for notifications (PROJECT.md §5.16).

Notifications are throttled two ways, both pure and deterministic here so the
service can be tested with an injected clock: a **quiet-hours** window during
which nothing is posted (``"HH:MM-HH:MM"``, wrapping past midnight), and a
**daily cap** on how many post per calendar day.
"""

from __future__ import annotations

from datetime import datetime, time

__all__ = ["day_key", "in_quiet_hours", "parse_quiet_hours"]


def _parse_hhmm(value: str) -> time:
    """Parse a ``"HH:MM"`` string into a :class:`~datetime.time`.

    Raises:
        ValueError: If ``value`` is not two colon-separated integers forming a
            valid 24-hour time.
    """
    hour_str, _, minute_str = value.strip().partition(":")
    hour, minute = int(hour_str), int(minute_str)
    return time(hour=hour, minute=minute)


def parse_quiet_hours(spec: str) -> tuple[time, time] | None:
    """Parse a ``"HH:MM-HH:MM"`` quiet-hours window.

    Args:
        spec: The window string; empty / whitespace means "no quiet hours".

    Returns:
        A ``(start, end)`` pair, or ``None`` when ``spec`` is empty or malformed
        (a bad window disables quiet hours rather than crashing the daemon).
    """
    if not spec.strip():
        return None
    start_str, sep, end_str = spec.partition("-")
    if not sep:
        return None
    try:
        return _parse_hhmm(start_str), _parse_hhmm(end_str)
    except ValueError:
        return None


def in_quiet_hours(now: datetime, spec: str) -> bool:
    """Return whether ``now`` falls inside the ``spec`` quiet-hours window.

    The window may wrap past midnight (``start > end``, e.g. ``"22:00-08:00"``),
    in which case a time counts as inside when it is at/after ``start`` **or**
    before ``end``. An empty or malformed ``spec`` is never quiet.
    """
    window = parse_quiet_hours(spec)
    if window is None:
        return False
    start, end = window
    moment = now.time()
    if start <= end:
        return start <= moment < end
    # Wraps past midnight: inside if after start OR before end.
    return moment >= start or moment < end


def day_key(now: datetime) -> str:
    """Return a stable per-calendar-day key (``"YYYY-MM-DD"``) for the daily cap."""
    return now.strftime("%Y-%m-%d")
