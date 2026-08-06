"""Tests for the tracking repository queries in :mod:`atlas.tracking.repository`."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from atlas.db import session_scope
from atlas.profiles.preferences import ProfilePreferences
from atlas.profiles.repository import create_profile
from atlas.scrape.repository import (
    create_job_posting,
    get_or_create_company,
    get_or_create_url_source,
)
from atlas.tailor.repository import get_or_create_application
from atlas.tracking.repository import count_applications_by_status, upcoming_deadlines
from atlas.tracking.service import set_application_status
from atlas.tracking.status import ApplicationStatus

if TYPE_CHECKING:
    from sqlalchemy.engine import Engine

_NOW = datetime(2026, 8, 4, tzinfo=UTC)


def _seed(engine: Engine, *, profile_name: str, title: str) -> int:
    """Create a posting + profile + application; return the profile id."""
    with session_scope(engine) as session:
        company = get_or_create_company(session, name="Acme")
        source = get_or_create_url_source(session)
        assert company.id is not None
        assert source.id is not None
        posting = create_job_posting(
            session,
            source_id=source.id,
            company_id=company.id,
            title=title,
            apply_url=f"https://jobs.acme.test/{title}",
            dedupe_hash=title,
            fetched_at=_NOW,
        )
        profile = create_profile(
            session, name=profile_name, preferences=ProfilePreferences(), active=True
        )
        assert posting.id is not None
        assert profile.id is not None
        get_or_create_application(
            session, job_posting_id=posting.id, profile_id=profile.id, clock=_NOW
        )
        return profile.id


def _seed_application(engine: Engine, *, title: str) -> int:
    """Create a posting + profile + application; return the application id."""
    with session_scope(engine) as session:
        company = get_or_create_company(session, name="Acme")
        source = get_or_create_url_source(session)
        assert company.id is not None
        assert source.id is not None
        posting = create_job_posting(
            session,
            source_id=source.id,
            company_id=company.id,
            title=title,
            apply_url=f"https://jobs.acme.test/{title}",
            dedupe_hash=title,
            fetched_at=_NOW,
        )
        profile = create_profile(session, name=title, preferences=ProfilePreferences(), active=True)
        assert posting.id is not None
        assert profile.id is not None
        application = get_or_create_application(
            session, job_posting_id=posting.id, profile_id=profile.id, clock=_NOW
        )
        assert application.id is not None
        return application.id


def test_count_by_status_empty(db_engine: Engine) -> None:
    with session_scope(db_engine) as session:
        assert count_applications_by_status(session) == {}


def test_count_by_status_totals(db_engine: Engine) -> None:
    _seed(db_engine, profile_name="BE", title="Backend")
    _seed(db_engine, profile_name="ML", title="ML")
    with session_scope(db_engine) as session:
        counts = count_applications_by_status(session)
    # Both freshly-created applications sit in "preparing".
    assert counts == {"preparing": 2}


def test_count_by_status_filters_by_profile(db_engine: Engine) -> None:
    first = _seed(db_engine, profile_name="BE", title="Backend")
    _seed(db_engine, profile_name="ML", title="ML")
    with session_scope(db_engine) as session:
        counts = count_applications_by_status(session, profile_id=first)
    assert counts == {"preparing": 1}


# --- upcoming_deadlines ----------------------------------------------------------


def _record_deadline(
    engine: Engine,
    application_id: int,
    *,
    target: ApplicationStatus,
    due: datetime | None,
) -> None:
    """Move an application to ``target`` (forced), recording ``due`` in history."""
    with session_scope(engine) as session:
        set_application_status(
            session, application_id, target, force=True, due=due, clock=lambda: _NOW
        )


def test_upcoming_deadlines_empty(db_engine: Engine) -> None:
    with session_scope(db_engine) as session:
        assert upcoming_deadlines(session, now=_NOW, lead_hours=24) == []


def test_upcoming_deadlines_within_window(db_engine: Engine) -> None:
    app_id = _seed_application(db_engine, title="Backend")
    due = _NOW + timedelta(hours=6)
    _record_deadline(db_engine, app_id, target=ApplicationStatus.OA, due=due)
    with session_scope(db_engine) as session:
        items = upcoming_deadlines(session, now=_NOW, lead_hours=24)
    assert len(items) == 1
    assert items[0].application_id == app_id
    assert items[0].status == "oa"
    assert items[0].due == due
    assert items[0].key == f"{app_id}:{due.isoformat()}"


def test_upcoming_deadlines_excludes_beyond_lead(db_engine: Engine) -> None:
    app_id = _seed_application(db_engine, title="Backend")
    _record_deadline(db_engine, app_id, target=ApplicationStatus.OA, due=_NOW + timedelta(hours=48))
    with session_scope(db_engine) as session:
        assert upcoming_deadlines(session, now=_NOW, lead_hours=24) == []


def test_upcoming_deadlines_excludes_past(db_engine: Engine) -> None:
    app_id = _seed_application(db_engine, title="Backend")
    _record_deadline(db_engine, app_id, target=ApplicationStatus.OA, due=_NOW - timedelta(hours=1))
    with session_scope(db_engine) as session:
        assert upcoming_deadlines(session, now=_NOW, lead_hours=24) == []


def test_upcoming_deadlines_ignores_entries_without_a_due(db_engine: Engine) -> None:
    app_id = _seed_application(db_engine, title="Backend")
    _record_deadline(db_engine, app_id, target=ApplicationStatus.OA, due=None)
    with session_scope(db_engine) as session:
        assert upcoming_deadlines(session, now=_NOW, lead_hours=24) == []


def test_upcoming_deadlines_skips_terminal_applications(db_engine: Engine) -> None:
    app_id = _seed_application(db_engine, title="Backend")
    due = _NOW + timedelta(hours=6)
    _record_deadline(db_engine, app_id, target=ApplicationStatus.INTERVIEW, due=due)
    # A rejection is terminal — its (still-future) interview deadline is moot.
    _record_deadline(db_engine, app_id, target=ApplicationStatus.REJECTED, due=None)
    with session_scope(db_engine) as session:
        assert upcoming_deadlines(session, now=_NOW, lead_hours=24) == []


def test_upcoming_deadlines_skips_malformed_history_entry(db_engine: Engine) -> None:
    app_id = _seed_application(db_engine, title="Backend")
    due = _NOW + timedelta(hours=6)
    _record_deadline(db_engine, app_id, target=ApplicationStatus.OA, due=due)
    # Inject a hand-mangled history entry that fails validation.
    with session_scope(db_engine) as session:
        from atlas.tailor.repository import get_application

        application = get_application(session, app_id)
        application.status_history = [*application.status_history, {"garbage": True}]
    with session_scope(db_engine) as session:
        items = upcoming_deadlines(session, now=_NOW, lead_hours=24)
    # The good entry survives; the malformed one is skipped, not fatal.
    assert [item.due for item in items] == [due]


def test_upcoming_deadlines_sorted_soonest_first(db_engine: Engine) -> None:
    app_id = _seed_application(db_engine, title="Backend")
    later = _NOW + timedelta(hours=20)
    sooner = _NOW + timedelta(hours=3)
    _record_deadline(db_engine, app_id, target=ApplicationStatus.OA, due=later)
    _record_deadline(db_engine, app_id, target=ApplicationStatus.INTERVIEW, due=sooner)
    with session_scope(db_engine) as session:
        items = upcoming_deadlines(session, now=_NOW, lead_hours=24)
    assert [item.due for item in items] == [sooner, later]
