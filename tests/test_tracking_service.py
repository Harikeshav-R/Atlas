"""Tests for status-transition orchestration in :mod:`atlas.tracking.service`."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytest

from atlas.db import session_scope
from atlas.db.models import Application
from atlas.profiles.preferences import ProfilePreferences
from atlas.profiles.repository import create_profile
from atlas.scrape.repository import (
    create_job_posting,
    get_or_create_company,
    get_or_create_url_source,
)
from atlas.tailor.errors import ApplicationNotFoundError
from atlas.tailor.repository import get_or_create_application
from atlas.tracking.errors import InvalidStatusTransitionError
from atlas.tracking.service import mark_applied, set_application_status
from atlas.tracking.status import ApplicationStatus

if TYPE_CHECKING:
    from collections.abc import Callable

    from sqlalchemy.engine import Engine

_CREATED = datetime(2026, 8, 3, 12, 0, tzinfo=UTC)
_NOW = datetime(2026, 8, 4, 9, 30, tzinfo=UTC)


def _fixed_clock(moment: datetime) -> Callable[[], datetime]:
    return lambda: moment


def _seed_application(engine: Engine) -> int:
    """Create a posting + profile + application (status ``preparing``); return its id."""
    with session_scope(engine) as session:
        company = get_or_create_company(session, name="Acme")
        source = get_or_create_url_source(session)
        assert company.id is not None
        assert source.id is not None
        posting = create_job_posting(
            session,
            source_id=source.id,
            company_id=company.id,
            title="Backend Engineer",
            apply_url="https://jobs.acme.test/1",
            dedupe_hash="hash",
            fetched_at=_CREATED,
        )
        profile = create_profile(session, name="BE", preferences=ProfilePreferences(), active=True)
        assert posting.id is not None
        assert profile.id is not None
        application = get_or_create_application(
            session, job_posting_id=posting.id, profile_id=profile.id, clock=_CREATED
        )
        assert application.id is not None
        return application.id


def test_set_status_records_history_and_bumps_updated_at(db_engine: Engine) -> None:
    app_id = _seed_application(db_engine)
    with session_scope(db_engine) as session:
        outcome = set_application_status(
            session, app_id, ApplicationStatus.READY, clock=_fixed_clock(_NOW)
        )
    assert outcome.previous_status == "preparing"
    assert outcome.new_status == "ready"
    assert outcome.applied_at is None
    assert outcome.outcome is None
    assert outcome.forced is False
    with session_scope(db_engine) as session:
        application = session.get(Application, app_id)
        assert application is not None
        assert application.status == "ready"
        assert application.updated_at == _NOW
        assert len(application.status_history) == 1
        entry = application.status_history[0]
        assert entry["from_status"] == "preparing"
        assert entry["to_status"] == "ready"
        assert datetime.fromisoformat(entry["at"]) == _NOW


def test_set_status_history_grows_across_transitions(db_engine: Engine) -> None:
    app_id = _seed_application(db_engine)
    for target in (ApplicationStatus.READY, ApplicationStatus.APPLIED):
        with session_scope(db_engine) as session:
            set_application_status(session, app_id, target, clock=_fixed_clock(_NOW))
    with session_scope(db_engine) as session:
        application = session.get(Application, app_id)
        assert application is not None
        assert [e["to_status"] for e in application.status_history] == ["ready", "applied"]


def test_invalid_transition_raises(db_engine: Engine) -> None:
    app_id = _seed_application(db_engine)
    with session_scope(db_engine) as session, pytest.raises(InvalidStatusTransitionError) as info:
        set_application_status(session, app_id, ApplicationStatus.OFFER)
    assert info.value.current is ApplicationStatus.PREPARING
    assert info.value.target is ApplicationStatus.OFFER
    assert "--force" in str(info.value)


def test_force_overrides_invalid_transition(db_engine: Engine) -> None:
    app_id = _seed_application(db_engine)
    with session_scope(db_engine) as session:
        outcome = set_application_status(
            session, app_id, ApplicationStatus.OFFER, force=True, clock=_fixed_clock(_NOW)
        )
    assert outcome.new_status == "offer"
    assert outcome.forced is True
    with session_scope(db_engine) as session:
        application = session.get(Application, app_id)
        assert application is not None
        assert application.status_history[0]["forced"] is True


def test_reaching_applied_stamps_applied_at_once(db_engine: Engine) -> None:
    app_id = _seed_application(db_engine)
    for target in (ApplicationStatus.READY, ApplicationStatus.APPLIED):
        with session_scope(db_engine) as session:
            set_application_status(session, app_id, target, clock=_fixed_clock(_NOW))
    # A later forced move back to applied must not overwrite the original date.
    later = datetime(2026, 8, 10, tzinfo=UTC)
    with session_scope(db_engine) as session:
        set_application_status(
            session, app_id, ApplicationStatus.APPLIED, force=True, clock=_fixed_clock(later)
        )
    with session_scope(db_engine) as session:
        application = session.get(Application, app_id)
        assert application is not None
        assert application.applied_at == _NOW


def test_terminal_status_records_outcome(db_engine: Engine) -> None:
    app_id = _seed_application(db_engine)
    with session_scope(db_engine) as session:
        outcome = set_application_status(
            session, app_id, ApplicationStatus.WITHDRAWN, clock=_fixed_clock(_NOW)
        )
    assert outcome.outcome == "withdrawn"
    with session_scope(db_engine) as session:
        application = session.get(Application, app_id)
        assert application is not None
        assert application.outcome == "withdrawn"


def test_set_status_records_due(db_engine: Engine) -> None:
    app_id = _seed_application(db_engine)
    for target in (ApplicationStatus.READY, ApplicationStatus.APPLIED):
        with session_scope(db_engine) as session:
            set_application_status(session, app_id, target, clock=_fixed_clock(_NOW))
    due = datetime(2026, 8, 15, tzinfo=UTC)
    with session_scope(db_engine) as session:
        outcome = set_application_status(
            session, app_id, ApplicationStatus.OA, due=due, clock=_fixed_clock(_NOW)
        )
    assert outcome.due == due
    with session_scope(db_engine) as session:
        application = session.get(Application, app_id)
        assert application is not None
        assert datetime.fromisoformat(application.status_history[-1]["due"]) == due


def test_mark_applied_moves_to_applied(db_engine: Engine) -> None:
    app_id = _seed_application(db_engine)
    with session_scope(db_engine) as session:
        set_application_status(session, app_id, ApplicationStatus.READY, clock=_fixed_clock(_NOW))
    with session_scope(db_engine) as session:
        outcome = mark_applied(session, app_id, clock=_fixed_clock(_NOW))
    assert outcome.new_status == "applied"
    assert outcome.applied_at == _NOW


def test_mark_applied_invalid_from_preparing(db_engine: Engine) -> None:
    app_id = _seed_application(db_engine)
    with session_scope(db_engine) as session, pytest.raises(InvalidStatusTransitionError):
        mark_applied(session, app_id)


def test_mark_applied_force_from_preparing(db_engine: Engine) -> None:
    app_id = _seed_application(db_engine)
    with session_scope(db_engine) as session:
        outcome = mark_applied(session, app_id, force=True, clock=_fixed_clock(_NOW))
    assert outcome.new_status == "applied"


def test_unknown_application_raises(db_engine: Engine) -> None:
    with session_scope(db_engine) as session, pytest.raises(ApplicationNotFoundError):
        set_application_status(session, 999, ApplicationStatus.READY)
