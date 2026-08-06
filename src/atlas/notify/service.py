"""The after-poll desktop-notification orchestrator (PROJECT.md §5.16).

:func:`notify_after_poll` is called after the daemon's scoring poll (from both the
scheduled tick and the on-demand IPC poll). It reads the freshly-scored high-fit
matches for every profile and the upcoming deadlines, posts a native notification
per newly-surfaced item — best-effort, so a dead backend never breaks the poll —
and advances the persisted run-state so a re-poll never re-alerts. Two throttles
apply: a quiet-hours window and a per-day cap.

Like the domain services, this is a pure function over an **open** session with
every boundary injected (the notifier, the clock, and the mutable run-state), so
the hermetic suite drives it with a :class:`~tests.conftest.FakeNotifier`, a fixed
clock, and an in-memory engine.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel

from atlas.db.models import Company
from atlas.matching.repository import list_new_high_fit
from atlas.notify.emit import notify_best_effort
from atlas.notify.window import day_key, in_quiet_hours
from atlas.profiles.repository import list_profiles
from atlas.resume.service import utcnow
from atlas.tracking.repository import upcoming_deadlines

if TYPE_CHECKING:
    from collections.abc import Callable
    from datetime import datetime

    from sqlmodel import Session

    from atlas.config.schema import NotificationsConfig
    from atlas.notify.state import NotifyState
    from atlas.platform.notifier import Notifier

__all__ = ["NotifyOutcome", "notify_after_poll"]


class NotifyOutcome(BaseModel):
    """The result of one after-poll notification pass.

    Attributes:
        matches: How many new high-fit matches were notified about.
        deadlines: How many upcoming deadlines were notified about.
        suppressed: Whether the whole pass was suppressed up front (notifications
            disabled or inside quiet hours) — no items were considered.
    """

    matches: int = 0
    deadlines: int = 0
    suppressed: bool = False


def notify_after_poll(
    session: Session,
    *,
    config: NotificationsConfig,
    notifier: Notifier,
    state: NotifyState,
    clock: Callable[[], datetime] = utcnow,
) -> NotifyOutcome:
    """Post desktop notifications for new matches and deadlines, best-effort.

    Mutates ``state`` in place (advancing the score high-water mark, the deadline
    keys, and the per-day count); the caller persists it. Returns a
    :class:`NotifyOutcome` for logging/tests. Never raises for a notification
    failure — each post goes through :func:`~atlas.notify.emit.notify_best_effort`.

    Args:
        session: The open session to read matches/deadlines within.
        config: The ``[notifications]`` settings (enable flag, thresholds, quiet
            hours, daily cap).
        notifier: The OS notification boundary to post through.
        state: The persisted run-state, mutated in place.
        clock: Injected clock (defaults to :func:`~atlas.resume.service.utcnow`).
    """
    now = clock()
    if not config.enabled or in_quiet_hours(now, config.quiet_hours):
        return NotifyOutcome(suppressed=True)

    # Roll the daily-cap counter over at a day boundary.
    today = day_key(now)
    if state.day != today:
        state.day = today
        state.daily_count = 0

    outcome = NotifyOutcome()

    # New high-fit matches, across every profile. Query every profile against the
    # *same* baseline high-water mark (score ids interleave across profiles, so
    # advancing it mid-loop would skip another profile's low-id rows), then bump
    # the mark once to the highest id seen.
    baseline = state.last_notified_score_id
    highest_seen = baseline
    for profile in list_profiles(session):
        if profile.id is None:  # pragma: no cover - persisted rows always have an id
            continue
        rows = list_new_high_fit(
            session,
            profile.id,
            min_score=config.min_match_score,
            after_score_id=baseline,
        )
        for posting, score in rows:
            assert score.id is not None  # a row filtered by id always has one
            highest_seen = max(highest_seen, score.id)
            if state.daily_count >= config.daily_cap:
                continue
            company = session.get(Company, posting.company_id)
            assert company is not None  # a non-null foreign key never misses
            notify_best_effort(
                notifier,
                "New job match",
                f"{company.name} — {posting.title} (fit {score.score})",
            )
            state.daily_count += 1
            outcome.matches += 1
    state.last_notified_score_id = highest_seen

    # Upcoming deadlines, dedup by their stable key.
    for item in upcoming_deadlines(session, now=now, lead_hours=config.deadline_lead_hours):
        if item.key in state.notified_deadline_keys:
            continue
        state.notified_deadline_keys.append(item.key)
        if state.daily_count >= config.daily_cap:
            continue
        notify_best_effort(
            notifier,
            "Deadline approaching",
            f"{item.status.upper()} due {item.due:%Y-%m-%d %H:%M} UTC",
        )
        state.daily_count += 1
        outcome.deadlines += 1

    return outcome
