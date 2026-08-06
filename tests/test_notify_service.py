"""Tests for the after-poll notification orchestrator in :mod:`atlas.notify.service`."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from atlas.config.schema import NotificationsConfig
from atlas.db import session_scope
from atlas.matching.repository import create_match_score
from atlas.notify.service import notify_after_poll
from atlas.notify.state import NotifyState
from atlas.profiles.preferences import ProfilePreferences
from atlas.profiles.repository import create_profile
from atlas.scrape.repository import (
    create_job_posting,
    get_or_create_company,
    get_or_create_url_source,
)
from atlas.tailor.repository import get_or_create_application
from atlas.tracking.service import set_application_status
from atlas.tracking.status import ApplicationStatus
from tests.conftest import FakeNotifier

if TYPE_CHECKING:
    from sqlalchemy.engine import Engine

_NOW = datetime(2026, 8, 6, 12, 0, tzinfo=UTC)


def _clock() -> datetime:
    return _NOW


def _seed_profile(engine: Engine, *, name: str = "Backend", active: bool = True) -> int:
    with session_scope(engine) as session:
        profile = create_profile(
            session, name=name, preferences=ProfilePreferences(), active=active
        )
        assert profile.id is not None
        return profile.id


def _seed_posting(engine: Engine, *, title: str, company: str = "Acme") -> int:
    with session_scope(engine) as session:
        company_row = get_or_create_company(session, name=company)
        source = get_or_create_url_source(session)
        assert company_row.id is not None
        assert source.id is not None
        posting = create_job_posting(
            session,
            source_id=source.id,
            company_id=company_row.id,
            title=title,
            apply_url=f"https://jobs.test/{title}",
            dedupe_hash=title,
            fetched_at=_NOW,
        )
        assert posting.id is not None
        return posting.id


def _score(engine: Engine, *, posting_id: int, profile_id: int, score: int) -> int:
    with session_scope(engine) as session:
        row = create_match_score(
            session,
            job_posting_id=posting_id,
            profile_id=profile_id,
            score=score,
            verdict="good",
            rationale="Solid overlap.",
            matched_strengths=["Python"],
            gaps=[],
            dealbreaker_hits=[],
            salary_fit="within",
            signals={},
            model="fake-model",
            created_at=_NOW,
        )
        assert row.id is not None
        return row.id


def _enabled(**overrides: object) -> NotificationsConfig:
    base: dict[str, object] = {
        "enabled": True,
        "min_match_score": 80,
        "deadline_lead_hours": 24,
        "quiet_hours": "",  # never quiet, for deterministic tests
        "daily_cap": 20,
    }
    base.update(overrides)
    return NotificationsConfig(**base)  # type: ignore[arg-type]


def test_disabled_suppresses_everything(db_engine: Engine) -> None:
    profile_id = _seed_profile(db_engine)
    posting_id = _seed_posting(db_engine, title="Backend")
    _score(db_engine, posting_id=posting_id, profile_id=profile_id, score=95)
    notifier = FakeNotifier()
    state = NotifyState()
    with session_scope(db_engine) as session:
        outcome = notify_after_poll(
            session,
            config=NotificationsConfig(enabled=False),
            notifier=notifier,
            state=state,
            clock=_clock,
        )
    assert outcome.suppressed is True
    assert notifier.notifications == []


def test_quiet_hours_suppresses_everything(db_engine: Engine) -> None:
    profile_id = _seed_profile(db_engine)
    posting_id = _seed_posting(db_engine, title="Backend")
    _score(db_engine, posting_id=posting_id, profile_id=profile_id, score=95)
    notifier = FakeNotifier()
    with session_scope(db_engine) as session:
        outcome = notify_after_poll(
            session,
            # _NOW is 12:00; a window covering noon suppresses.
            config=_enabled(quiet_hours="11:00-13:00"),
            notifier=notifier,
            state=NotifyState(),
            clock=_clock,
        )
    assert outcome.suppressed is True
    assert notifier.notifications == []


def test_notifies_new_high_fit_match(db_engine: Engine) -> None:
    profile_id = _seed_profile(db_engine)
    posting_id = _seed_posting(db_engine, title="Backend Engineer", company="Acme")
    score_id = _score(db_engine, posting_id=posting_id, profile_id=profile_id, score=92)
    notifier = FakeNotifier()
    state = NotifyState()
    with session_scope(db_engine) as session:
        outcome = notify_after_poll(
            session, config=_enabled(), notifier=notifier, state=state, clock=_clock
        )
    assert outcome.matches == 1
    assert notifier.notifications == [("New job match", "Acme — Backend Engineer (fit 92)")]
    # The high-water mark advanced past the notified score.
    assert state.last_notified_score_id == score_id
    assert state.daily_count == 1
    assert state.day == "2026-08-06"


def test_below_threshold_is_not_notified(db_engine: Engine) -> None:
    profile_id = _seed_profile(db_engine)
    posting_id = _seed_posting(db_engine, title="Backend")
    _score(db_engine, posting_id=posting_id, profile_id=profile_id, score=79)
    notifier = FakeNotifier()
    with session_scope(db_engine) as session:
        outcome = notify_after_poll(
            session, config=_enabled(), notifier=notifier, state=NotifyState(), clock=_clock
        )
    assert outcome.matches == 0
    assert notifier.notifications == []


def test_re_poll_does_not_renotify(db_engine: Engine) -> None:
    profile_id = _seed_profile(db_engine)
    posting_id = _seed_posting(db_engine, title="Backend")
    _score(db_engine, posting_id=posting_id, profile_id=profile_id, score=92)
    notifier = FakeNotifier()
    state = NotifyState()
    with session_scope(db_engine) as session:
        notify_after_poll(session, config=_enabled(), notifier=notifier, state=state, clock=_clock)
    # A second pass with no new scores notifies nothing.
    with session_scope(db_engine) as session:
        outcome = notify_after_poll(
            session, config=_enabled(), notifier=notifier, state=state, clock=_clock
        )
    assert outcome.matches == 0
    assert len(notifier.notifications) == 1


def test_matches_across_multiple_profiles_use_same_baseline(db_engine: Engine) -> None:
    # Two profiles' high-fit scores interleave by id; both must be notified.
    p_a = _seed_profile(db_engine, name="A", active=True)
    p_b = _seed_profile(db_engine, name="B", active=False)
    posting_id = _seed_posting(db_engine, title="Backend")
    _score(db_engine, posting_id=posting_id, profile_id=p_a, score=90)
    _score(db_engine, posting_id=posting_id, profile_id=p_b, score=95)
    notifier = FakeNotifier()
    with session_scope(db_engine) as session:
        outcome = notify_after_poll(
            session, config=_enabled(), notifier=notifier, state=NotifyState(), clock=_clock
        )
    assert outcome.matches == 2


def test_daily_cap_limits_matches(db_engine: Engine) -> None:
    profile_id = _seed_profile(db_engine)
    p1 = _seed_posting(db_engine, title="Backend")
    p2 = _seed_posting(db_engine, title="Platform")
    _score(db_engine, posting_id=p1, profile_id=profile_id, score=90)
    last = _score(db_engine, posting_id=p2, profile_id=profile_id, score=95)
    notifier = FakeNotifier()
    state = NotifyState()
    with session_scope(db_engine) as session:
        outcome = notify_after_poll(
            session, config=_enabled(daily_cap=1), notifier=notifier, state=state, clock=_clock
        )
    # Only one posted, but the high-water mark still advances past both so the
    # capped-out match is not re-considered forever.
    assert outcome.matches == 1
    assert len(notifier.notifications) == 1
    assert state.last_notified_score_id == last
    assert state.daily_count == 1


def test_day_rollover_resets_the_cap(db_engine: Engine) -> None:
    profile_id = _seed_profile(db_engine)
    posting_id = _seed_posting(db_engine, title="Backend")
    _score(db_engine, posting_id=posting_id, profile_id=profile_id, score=90)
    notifier = FakeNotifier()
    # Yesterday's state was already at the cap.
    state = NotifyState(day="2026-08-05", daily_count=20)
    with session_scope(db_engine) as session:
        notify_after_poll(
            session, config=_enabled(daily_cap=20), notifier=notifier, state=state, clock=_clock
        )
    # The new day reset the counter, so today's match posts.
    assert state.day == "2026-08-06"
    assert state.daily_count == 1
    assert len(notifier.notifications) == 1


# --- deadlines -------------------------------------------------------------------


def _seed_application_with_deadline(
    engine: Engine, *, hours_ahead: float, target: ApplicationStatus = ApplicationStatus.OA
) -> int:
    with session_scope(engine) as session:
        company = get_or_create_company(session, name="Acme")
        source = get_or_create_url_source(session)
        assert company.id is not None
        assert source.id is not None
        posting = create_job_posting(
            session,
            source_id=source.id,
            company_id=company.id,
            title="Backend",
            apply_url="https://jobs.test/dl",
            dedupe_hash="dl",
            fetched_at=_NOW,
        )
        profile = create_profile(session, name="DL", preferences=ProfilePreferences(), active=True)
        assert posting.id is not None
        assert profile.id is not None
        application = get_or_create_application(
            session, job_posting_id=posting.id, profile_id=profile.id, clock=_NOW
        )
        assert application.id is not None
        app_id = application.id
    with session_scope(engine) as session:
        set_application_status(
            session,
            app_id,
            target,
            force=True,
            due=_NOW + timedelta(hours=hours_ahead),
            clock=_clock,
        )
    return app_id


def test_notifies_upcoming_deadline(db_engine: Engine) -> None:
    _seed_application_with_deadline(db_engine, hours_ahead=6)
    notifier = FakeNotifier()
    state = NotifyState()
    with session_scope(db_engine) as session:
        outcome = notify_after_poll(
            session, config=_enabled(), notifier=notifier, state=state, clock=_clock
        )
    assert outcome.deadlines == 1
    assert notifier.notifications[0][0] == "Deadline approaching"
    assert "OA due 2026-08-06 18:00 UTC" in notifier.notifications[0][1]
    assert len(state.notified_deadline_keys) == 1


def test_deadline_notified_once(db_engine: Engine) -> None:
    _seed_application_with_deadline(db_engine, hours_ahead=6)
    notifier = FakeNotifier()
    state = NotifyState()
    with session_scope(db_engine) as session:
        notify_after_poll(session, config=_enabled(), notifier=notifier, state=state, clock=_clock)
    with session_scope(db_engine) as session:
        outcome = notify_after_poll(
            session, config=_enabled(), notifier=notifier, state=state, clock=_clock
        )
    assert outcome.deadlines == 0
    assert len(notifier.notifications) == 1


def test_deadline_respects_daily_cap(db_engine: Engine) -> None:
    _seed_application_with_deadline(db_engine, hours_ahead=6)
    notifier = FakeNotifier()
    # Cap already reached before deadlines are considered.
    state = NotifyState(day="2026-08-06", daily_count=20)
    with session_scope(db_engine) as session:
        outcome = notify_after_poll(
            session, config=_enabled(daily_cap=20), notifier=notifier, state=state, clock=_clock
        )
    assert outcome.deadlines == 0
    assert notifier.notifications == []
    # The key is still recorded, so it will not fire once the cap resets tomorrow
    # for a deadline that has by then passed — recorded to avoid a late duplicate.
    assert len(state.notified_deadline_keys) == 1


def test_raising_notifier_is_swallowed(db_engine: Engine) -> None:
    from atlas.platform.notifier import NotifyError

    profile_id = _seed_profile(db_engine)
    posting_id = _seed_posting(db_engine, title="Backend")
    _score(db_engine, posting_id=posting_id, profile_id=profile_id, score=90)
    notifier = FakeNotifier(raises=NotifyError("no D-Bus"))
    state = NotifyState()
    with session_scope(db_engine) as session:
        # A failing backend must not raise out of the pass.
        outcome = notify_after_poll(
            session, config=_enabled(), notifier=notifier, state=state, clock=_clock
        )
    # The match was counted and the high-water mark advanced even though the post failed.
    assert outcome.matches == 1
    assert state.daily_count == 1
