"""Tests for the cover-letter orchestration in :mod:`atlas.coverletter.service`."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytest

from atlas.coverletter.errors import (
    CoverLetterOutputError,
    NoActiveProfileError,
    NoMasterResumeError,
)
from atlas.coverletter.repository import get_latest_cover_letter
from atlas.coverletter.service import CoverLetterOutcome, write_application_cover_letter
from atlas.db import session_scope
from atlas.profiles.preferences import ProfilePreferences
from atlas.profiles.repository import create_profile, get_active_profile, upsert_user
from atlas.resume.repository import create_version
from atlas.resume.structure import BlockType, ParsedBlock, ParsedResume
from atlas.scrape.errors import JobPostingNotFoundError
from atlas.scrape.repository import (
    create_job_posting,
    get_or_create_company,
    get_or_create_url_source,
    get_posting,
)
from atlas.tailor.repository import create_tailored_resume, get_or_create_application
from tests.conftest import FakeLLMProvider, FakePdfRenderer, make_response

if TYPE_CHECKING:
    from datetime import datetime as _dt
    from pathlib import Path

    from sqlalchemy.engine import Engine

_NOW = datetime(2026, 8, 4, 12, 0, tzinfo=UTC)


def _fixed_clock() -> _dt:
    return _NOW


def _draft() -> dict[str, object]:
    return {
        "greeting": "Dear Hiring Manager,",
        "hook": "I am excited to apply.",
        "body_paragraphs": ["I led a platform team."],
        "closing": "Sincerely,",
        "gaps": ["Kubernetes"],
    }


def _seed_posting(engine: Engine) -> int:
    with session_scope(engine) as session:
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
            description="Build",
            requirements={"must": ["Python"]},
            keywords=["python"],
        )
        assert posting.id is not None
        return posting.id


def _seed_profile(engine: Engine) -> None:
    with session_scope(engine) as session:
        create_profile(
            session,
            name="BE",
            preferences=ProfilePreferences(target_roles=["Backend Engineer"]),
            active=True,
        )


def _seed_resume(engine: Engine) -> None:
    with session_scope(engine) as session:
        upsert_user(session, name="Sam Lee", email="sam@example.com")
        parsed = ParsedResume(
            blocks=[
                ParsedBlock(
                    type=BlockType.EXPERIENCE,
                    content_id="blk_a",
                    position=0,
                    text="Staff Engineer, Acme",
                )
            ]
        )
        create_version(
            session, raw_markdown="# Sam", source_path="r.md", parsed=parsed, created_at=_NOW
        )


def _seed_all(engine: Engine) -> int:
    posting_id = _seed_posting(engine)
    _seed_profile(engine)
    _seed_resume(engine)
    return posting_id


def _cover(
    engine: Engine, posting_id: int, *, provider: FakeLLMProvider, tmp_path: Path
) -> CoverLetterOutcome:
    with session_scope(engine) as session:
        return write_application_cover_letter(
            session,
            posting_id,
            provider=provider,
            renderer=FakePdfRenderer(page_count=1),
            honesty_level="light_inference",
            theme="matching",
            clock=_fixed_clock,
            renders_dir=tmp_path,
        )


def test_write_cover_letter_grounds_on_master_resume(db_engine: Engine, tmp_path: Path) -> None:
    posting_id = _seed_all(db_engine)
    provider = FakeLLMProvider([make_response(structured=_draft())])
    outcome = _cover(db_engine, posting_id, provider=provider, tmp_path=tmp_path)
    assert outcome.company == "Globex"
    assert outcome.grounded_on == "master_resume"
    assert outcome.one_page is True
    assert outcome.gaps == ["Kubernetes"]
    assert outcome.path == str(tmp_path / "Sam_Lee__Globex__cover.pdf")
    assert (tmp_path / "Sam_Lee__Globex__cover.pdf").read_bytes() == b"%PDF-fake"
    with session_scope(db_engine) as session:
        latest = get_latest_cover_letter(session, outcome.application_id)
        assert latest is not None
        assert latest.rendered_pdf_ref == outcome.path
        assert latest.content["greeting"] == "Dear Hiring Manager,"


def test_write_cover_letter_grounds_on_tailored_resume(db_engine: Engine, tmp_path: Path) -> None:
    posting_id = _seed_all(db_engine)
    # Attach a tailored resume to the application so its selections ground the letter.
    with session_scope(db_engine) as session:
        profile = get_active_profile(session)
        assert profile is not None and profile.id is not None
        stored_posting = get_posting(session, posting_id)
        assert stored_posting.id is not None
        application = get_or_create_application(
            session, job_posting_id=stored_posting.id, profile_id=profile.id, clock=_NOW
        )
        assert application.id is not None
        create_tailored_resume(
            session,
            application_id=application.id,
            master_resume_version=1,
            selections=[
                {"content_id": "blk_a", "final_text": "Led the platform team", "included": True}
            ],
            final_content={"name": "Sam Lee", "sections": []},
            rendered_pdf_ref="renders/x.pdf",
            decisions=[],
            created_at=_NOW,
        )
    provider = FakeLLMProvider([make_response(structured=_draft())])
    outcome = _cover(db_engine, posting_id, provider=provider, tmp_path=tmp_path)
    assert outcome.grounded_on == "tailored_resume"
    # The tailored selection text reached the prompt as grounding material.
    assert "Led the platform team" in provider.calls[0].prompt


def test_write_cover_letter_falls_back_when_selections_empty(
    db_engine: Engine, tmp_path: Path
) -> None:
    # A tailored resume exists but all its selections are excluded/blank, so the
    # letter grounds on the master resume instead.
    posting_id = _seed_all(db_engine)
    with session_scope(db_engine) as session:
        profile = get_active_profile(session)
        assert profile is not None and profile.id is not None
        stored_posting = get_posting(session, posting_id)
        assert stored_posting.id is not None
        application = get_or_create_application(
            session, job_posting_id=stored_posting.id, profile_id=profile.id, clock=_NOW
        )
        assert application.id is not None
        create_tailored_resume(
            session,
            application_id=application.id,
            master_resume_version=1,
            selections=[{"content_id": "blk_a", "final_text": "", "included": False}],
            final_content={"name": "Sam Lee", "sections": []},
            rendered_pdf_ref=None,
            decisions=[],
            created_at=_NOW,
        )
    provider = FakeLLMProvider([make_response(structured=_draft())])
    outcome = _cover(db_engine, posting_id, provider=provider, tmp_path=tmp_path)
    assert outcome.grounded_on == "master_resume"


def test_write_cover_letter_unknown_posting_raises(db_engine: Engine, tmp_path: Path) -> None:
    _seed_profile(db_engine)
    _seed_resume(db_engine)
    with session_scope(db_engine) as session, pytest.raises(JobPostingNotFoundError):
        write_application_cover_letter(
            session,
            999,
            provider=FakeLLMProvider([]),
            renderer=FakePdfRenderer(),
            honesty_level="strict",
            theme="matching",
            renders_dir=tmp_path,
        )


def test_write_cover_letter_no_profile_raises(db_engine: Engine, tmp_path: Path) -> None:
    posting_id = _seed_posting(db_engine)
    _seed_resume(db_engine)
    with session_scope(db_engine) as session, pytest.raises(NoActiveProfileError):
        write_application_cover_letter(
            session,
            posting_id,
            provider=FakeLLMProvider([]),
            renderer=FakePdfRenderer(),
            honesty_level="strict",
            theme="matching",
            renders_dir=tmp_path,
        )


def test_write_cover_letter_no_material_raises(db_engine: Engine, tmp_path: Path) -> None:
    posting_id = _seed_posting(db_engine)
    _seed_profile(db_engine)  # profile but no resume and no tailored resume
    with session_scope(db_engine) as session, pytest.raises(NoMasterResumeError):
        write_application_cover_letter(
            session,
            posting_id,
            provider=FakeLLMProvider([]),
            renderer=FakePdfRenderer(),
            honesty_level="strict",
            theme="matching",
            renders_dir=tmp_path,
        )


def test_write_cover_letter_wraps_output_error(db_engine: Engine, tmp_path: Path) -> None:
    posting_id = _seed_all(db_engine)
    provider = FakeLLMProvider([make_response(text="no json") for _ in range(4)])
    with session_scope(db_engine) as session, pytest.raises(CoverLetterOutputError):
        write_application_cover_letter(
            session,
            posting_id,
            provider=provider,
            renderer=FakePdfRenderer(),
            honesty_level="strict",
            theme="matching",
            renders_dir=tmp_path,
        )
