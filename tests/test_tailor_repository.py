"""Tests for tailoring persistence in :mod:`atlas.tailor.repository`."""

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
from atlas.tailor.repository import (
    create_tailored_resume,
    get_latest_tailored_resume,
    get_or_create_application,
)

if TYPE_CHECKING:
    from sqlalchemy.engine import Engine

_NOW = datetime(2026, 8, 3, 12, 0, tzinfo=UTC)


def _seed_refs(engine: Engine) -> tuple[int, int]:
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
        return posting.id, profile.id


def test_get_or_create_application_is_idempotent(db_engine: Engine) -> None:
    posting_id, profile_id = _seed_refs(db_engine)
    with session_scope(db_engine) as session:
        first = get_or_create_application(
            session, job_posting_id=posting_id, profile_id=profile_id, clock=_NOW
        )
        assert first.id is not None
        assert first.status == "preparing"
        first_id = first.id
    with session_scope(db_engine) as session:
        again = get_or_create_application(
            session, job_posting_id=posting_id, profile_id=profile_id, clock=_NOW
        )
        assert again.id == first_id  # reused, not duplicated


def test_create_tailored_resume_versions_per_application(db_engine: Engine) -> None:
    posting_id, profile_id = _seed_refs(db_engine)
    with session_scope(db_engine) as session:
        application = get_or_create_application(
            session, job_posting_id=posting_id, profile_id=profile_id, clock=_NOW
        )
        assert application.id is not None
        app_id = application.id
    for expected_version in (1, 2):
        with session_scope(db_engine) as session:
            tailored = create_tailored_resume(
                session,
                application_id=app_id,
                master_resume_version=1,
                selections=[{"content_id": "blk_a"}],
                final_content={"name": "Sam"},
                rendered_pdf_ref=f"renders/v{expected_version}.pdf",
                decisions=[{"content_id": "blk_a", "included": True}],
                created_at=_NOW,
            )
            assert tailored.version == expected_version
    with session_scope(db_engine) as session:
        latest = get_latest_tailored_resume(session, app_id)
        assert latest is not None
        assert latest.version == 2


def test_get_latest_tailored_resume_none_when_absent(db_engine: Engine) -> None:
    with session_scope(db_engine) as session:
        assert get_latest_tailored_resume(session, 999) is None
