"""Tests for re-render / open orchestration in :mod:`atlas.materials.service`."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from atlas.coverletter.repository import create_cover_letter
from atlas.db import session_scope
from atlas.materials.service import RerenderOutcome, open_application, rerender_application
from atlas.profiles.preferences import ProfilePreferences
from atlas.profiles.repository import create_profile, upsert_user
from atlas.scrape.repository import (
    create_job_posting,
    get_or_create_company,
    get_or_create_url_source,
)
from atlas.tailor.errors import ApplicationNotFoundError
from atlas.tailor.repository import create_tailored_resume, get_or_create_application
from tests.conftest import FakeFileOpener, FakePdfRenderer

if TYPE_CHECKING:
    from datetime import datetime as _dt

    from sqlalchemy.engine import Engine

_NOW = datetime(2026, 8, 4, 12, 0, tzinfo=UTC)


def _fixed_clock() -> _dt:
    return _NOW


def _seed_application(engine: Engine) -> int:
    """Seed a user + posting + profile + application; return the application id."""
    with session_scope(engine) as session:
        upsert_user(session, name="Sam Lee", email="sam@example.com")
        company = get_or_create_company(session, name="Globex")
        source = get_or_create_url_source(session)
        assert company.id is not None
        assert source.id is not None
        posting = create_job_posting(
            session,
            source_id=source.id,
            company_id=company.id,
            title="Backend Engineer",
            apply_url="https://jobs.globex.test/1",
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


def _add_tailored(engine: Engine, application_id: int) -> None:
    with session_scope(engine) as session:
        create_tailored_resume(
            session,
            application_id=application_id,
            master_resume_version=1,
            selections=[],
            final_content={"name": "Sam Lee", "sections": []},
            rendered_pdf_ref="renders/old_resume.pdf",
            decisions=[],
            created_at=_NOW,
        )


def _add_cover(engine: Engine, application_id: int) -> None:
    with session_scope(engine) as session:
        create_cover_letter(
            session,
            application_id=application_id,
            content={"greeting": "Dear Hiring Manager,", "hook": "Hello.", "body_paragraphs": []},
            tone="professional",
            rendered_pdf_ref="renders/old_cover.pdf",
            created_at=_NOW,
        )


def _rerender(engine: Engine, application_id: int, tmp_path: Path) -> RerenderOutcome:
    with session_scope(engine) as session:
        return rerender_application(
            session,
            application_id,
            renderer=FakePdfRenderer(page_count=1),
            resume_theme="jakes-resume",
            cover_theme="matching",
            clock=_fixed_clock,
            renders_dir=tmp_path,
        )


def test_rerender_both_materials(db_engine: Engine, tmp_path: Path) -> None:
    app_id = _seed_application(db_engine)
    _add_tailored(db_engine, app_id)
    _add_cover(db_engine, app_id)
    outcome = _rerender(db_engine, app_id, tmp_path)
    assert outcome.resume_path == str(tmp_path / "Sam_Lee__Globex__tailored.pdf")
    assert outcome.cover_letter_path == str(tmp_path / "Sam_Lee__Globex__cover.pdf")
    assert (tmp_path / "Sam_Lee__Globex__tailored.pdf").exists()
    assert (tmp_path / "Sam_Lee__Globex__cover.pdf").exists()


def test_rerender_skips_missing_cover(db_engine: Engine, tmp_path: Path) -> None:
    app_id = _seed_application(db_engine)
    _add_tailored(db_engine, app_id)  # tailored resume only, no cover letter
    outcome = _rerender(db_engine, app_id, tmp_path)
    assert outcome.resume_path is not None
    assert outcome.cover_letter_path is None


def test_rerender_skips_missing_resume(db_engine: Engine, tmp_path: Path) -> None:
    app_id = _seed_application(db_engine)
    _add_cover(db_engine, app_id)  # cover only, no tailored resume
    outcome = _rerender(db_engine, app_id, tmp_path)
    assert outcome.resume_path is None
    assert outcome.cover_letter_path is not None


def test_rerender_unknown_application_raises(db_engine: Engine, tmp_path: Path) -> None:
    with session_scope(db_engine) as session, pytest.raises(ApplicationNotFoundError):
        rerender_application(
            session,
            999,
            renderer=FakePdfRenderer(),
            resume_theme="jakes-resume",
            cover_theme="matching",
            renders_dir=tmp_path,
        )


def test_open_opens_both_pdf_refs(db_engine: Engine) -> None:
    app_id = _seed_application(db_engine)
    _add_tailored(db_engine, app_id)
    _add_cover(db_engine, app_id)
    opener = FakeFileOpener()
    with session_scope(db_engine) as session:
        outcome = open_application(session, app_id, opener=opener)
    assert outcome.opened == ["renders/old_resume.pdf", "renders/old_cover.pdf"]
    # The opener receives Path objects; compare as Paths so the separator matches
    # the OS (Windows uses "\\", not "/").
    assert opener.opened == [Path("renders/old_resume.pdf"), Path("renders/old_cover.pdf")]


def test_open_skips_material_without_a_rendered_pdf(db_engine: Engine) -> None:
    # A tailored resume with no rendered_pdf_ref is skipped; the cover (which has
    # one) is still opened.
    app_id = _seed_application(db_engine)
    with session_scope(db_engine) as session:
        create_tailored_resume(
            session,
            application_id=app_id,
            master_resume_version=1,
            selections=[],
            final_content={},
            rendered_pdf_ref=None,
            decisions=[],
            created_at=_NOW,
        )
    _add_cover(db_engine, app_id)
    opener = FakeFileOpener()
    with session_scope(db_engine) as session:
        outcome = open_application(session, app_id, opener=opener)
    assert outcome.opened == ["renders/old_cover.pdf"]


def test_open_nothing_when_no_materials(db_engine: Engine) -> None:
    app_id = _seed_application(db_engine)
    opener = FakeFileOpener()
    with session_scope(db_engine) as session:
        outcome = open_application(session, app_id, opener=opener)
    assert outcome.opened == []
    assert opener.opened == []


def test_open_unknown_application_raises(db_engine: Engine) -> None:
    opener = FakeFileOpener()
    with session_scope(db_engine) as session, pytest.raises(ApplicationNotFoundError):
        open_application(session, 999, opener=opener)
