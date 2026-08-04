"""Tests for the tracking repository queries in :mod:`atlas.tracking.repository`."""

from __future__ import annotations

from datetime import UTC, datetime
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
from atlas.tracking.repository import count_applications_by_status

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
