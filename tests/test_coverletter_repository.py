"""Tests for cover-letter persistence in :mod:`atlas.coverletter.repository`."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from atlas.coverletter.repository import create_cover_letter, get_latest_cover_letter
from atlas.db import session_scope
from atlas.profiles.preferences import ProfilePreferences
from atlas.profiles.repository import create_profile
from atlas.scrape.repository import (
    create_job_posting,
    get_or_create_company,
    get_or_create_url_source,
)
from atlas.tailor.repository import get_or_create_application

if TYPE_CHECKING:
    from sqlalchemy.engine import Engine

_NOW = datetime(2026, 8, 4, 12, 0, tzinfo=UTC)


def _seed_application(engine: Engine) -> int:
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
            fetched_at=_NOW,
        )
        profile = create_profile(session, name="BE", preferences=ProfilePreferences(), active=True)
        assert posting.id is not None
        assert profile.id is not None
        application = get_or_create_application(
            session, job_posting_id=posting.id, profile_id=profile.id, clock=_NOW
        )
        assert application.id is not None
        return application.id


def test_create_cover_letter_versions_per_application(db_engine: Engine) -> None:
    app_id = _seed_application(db_engine)
    for expected_version in (1, 2):
        with session_scope(db_engine) as session:
            letter = create_cover_letter(
                session,
                application_id=app_id,
                content={"greeting": "Dear Hiring Manager,"},
                tone="professional",
                rendered_pdf_ref=f"renders/cover_v{expected_version}.pdf",
                created_at=_NOW,
            )
            assert letter.version == expected_version
    with session_scope(db_engine) as session:
        latest = get_latest_cover_letter(session, app_id)
        assert latest is not None
        assert latest.version == 2
        assert latest.content == {"greeting": "Dear Hiring Manager,"}


def test_get_latest_cover_letter_none_when_absent(db_engine: Engine) -> None:
    with session_scope(db_engine) as session:
        assert get_latest_cover_letter(session, 999) is None
