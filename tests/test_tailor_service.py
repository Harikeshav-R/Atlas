"""Tests for the tailoring orchestration in :mod:`atlas.tailor.service`."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytest

from atlas.db import session_scope
from atlas.profiles.preferences import ProfilePreferences
from atlas.profiles.repository import create_profile, upsert_user
from atlas.resume.repository import create_version
from atlas.resume.structure import BlockType, ParsedBlock, ParsedResume
from atlas.scrape.errors import JobPostingNotFoundError
from atlas.scrape.repository import (
    create_job_posting,
    get_or_create_company,
    get_or_create_url_source,
)
from atlas.tailor.errors import NoActiveProfileError, NoMasterResumeError, TailoringOutputError
from atlas.tailor.repository import get_latest_tailored_resume
from atlas.tailor.service import tailor_posting
from tests.conftest import FakeLLMProvider, SequencedPdfRenderer, make_response

if TYPE_CHECKING:
    from datetime import datetime as _dt
    from pathlib import Path

    from sqlalchemy.engine import Engine

_NOW = datetime(2026, 8, 3, 12, 0, tzinfo=UTC)


def _fixed_clock() -> _dt:
    return _NOW


def _tailored(*, included: int = 2) -> dict[str, object]:
    items = [
        {
            "content_id": "blk_a",
            "block_type": "experience",
            "final_text": "Led platform team",
            "reason": "core",
            "included": True,
        },
        {
            "content_id": "blk_b",
            "block_type": "skill",
            "final_text": "Python, Go",
            "reason": "stack",
            "included": included >= 2,
        },
    ]
    return {"items": items, "gaps": ["Kubernetes"], "summary_rationale": "focus"}


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
            tailoring_emphasis=["distributed systems"],
            active=True,
        )


def _seed_resume(engine: Engine) -> None:
    with session_scope(engine) as session:
        upsert_user(session, name="Sam Lee")
        parsed = ParsedResume(
            blocks=[
                ParsedBlock(
                    type=BlockType.EXPERIENCE,
                    content_id="blk_a",
                    position=0,
                    text="Staff Engineer, Acme Jan 2020 - Mar 2026",
                ),
                ParsedBlock(
                    type=BlockType.SKILL, content_id="blk_b", position=1, text="Python, Go"
                ),
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


def test_tailor_posting_persists_and_renders(db_engine: Engine, tmp_path: Path) -> None:
    posting_id = _seed_all(db_engine)
    provider = FakeLLMProvider([make_response(structured=_tailored())])
    renderer = SequencedPdfRenderer([1])
    with session_scope(db_engine) as session:
        outcome = tailor_posting(
            session,
            posting_id,
            provider=provider,
            renderer=renderer,
            honesty_level="light_inference",
            theme="jakes-resume",
            clock=_fixed_clock,
            renders_dir=tmp_path,
        )
    assert outcome.posting_id == posting_id
    assert outcome.company == "Globex"
    assert outcome.one_page is True
    assert outcome.included_count == 2
    assert outcome.version == 1
    assert outcome.gaps == ["Kubernetes"]
    # PDF written under the injected dir; the tailored_resume row references it.
    assert outcome.path == str(tmp_path / "Sam_Lee__Globex__tailored.pdf")
    assert (tmp_path / "Sam_Lee__Globex__tailored.pdf").read_bytes() == b"%PDF-fake"
    # The rendered HTML carried the tailored (and date-restored) content.
    assert "Led platform team" in renderer.html_calls[0]
    assert "Jan 2020" in renderer.html_calls[0]  # date-restore safety net fired
    with session_scope(db_engine) as session:
        latest = get_latest_tailored_resume(session, outcome.application_id)
        assert latest is not None
        assert latest.master_resume_version == 1
        assert latest.rendered_pdf_ref == outcome.path


def test_tailor_posting_reuses_application_and_bumps_version(
    db_engine: Engine, tmp_path: Path
) -> None:
    posting_id = _seed_all(db_engine)
    provider = FakeLLMProvider(
        [make_response(structured=_tailored()), make_response(structured=_tailored())]
    )
    with session_scope(db_engine) as session:
        first = tailor_posting(
            session,
            posting_id,
            provider=provider,
            renderer=SequencedPdfRenderer([1]),
            honesty_level="strict",
            theme="jakes-resume",
            clock=_fixed_clock,
            renders_dir=tmp_path,
        )
    with session_scope(db_engine) as session:
        second = tailor_posting(
            session,
            posting_id,
            provider=provider,
            renderer=SequencedPdfRenderer([1]),
            honesty_level="strict",
            theme="jakes-resume",
            clock=_fixed_clock,
            renders_dir=tmp_path,
        )
    assert second.application_id == first.application_id  # reused
    assert (first.version, second.version) == (1, 2)  # append-only versioning


def test_tailor_posting_trims_to_one_page(db_engine: Engine, tmp_path: Path) -> None:
    posting_id = _seed_all(db_engine)
    provider = FakeLLMProvider([make_response(structured=_tailored())])
    renderer = SequencedPdfRenderer([2, 1])  # overflow, then fits after one trim
    with session_scope(db_engine) as session:
        outcome = tailor_posting(
            session,
            posting_id,
            provider=provider,
            renderer=renderer,
            honesty_level="light_inference",
            theme="jakes-resume",
            clock=_fixed_clock,
            renders_dir=tmp_path,
        )
    assert outcome.one_page is True
    assert outcome.trimmed == 1


def test_tailor_posting_unknown_id_raises(db_engine: Engine, tmp_path: Path) -> None:
    _seed_profile(db_engine)
    _seed_resume(db_engine)
    with session_scope(db_engine) as session, pytest.raises(JobPostingNotFoundError):
        tailor_posting(
            session,
            999,
            provider=FakeLLMProvider([]),
            renderer=SequencedPdfRenderer([1]),
            honesty_level="strict",
            theme="jakes-resume",
            renders_dir=tmp_path,
        )


def test_tailor_posting_no_active_profile_raises(db_engine: Engine, tmp_path: Path) -> None:
    posting_id = _seed_posting(db_engine)
    _seed_resume(db_engine)
    with session_scope(db_engine) as session, pytest.raises(NoActiveProfileError):
        tailor_posting(
            session,
            posting_id,
            provider=FakeLLMProvider([]),
            renderer=SequencedPdfRenderer([1]),
            honesty_level="strict",
            theme="jakes-resume",
            renders_dir=tmp_path,
        )


def test_tailor_posting_no_master_resume_raises(db_engine: Engine, tmp_path: Path) -> None:
    posting_id = _seed_posting(db_engine)
    _seed_profile(db_engine)
    with session_scope(db_engine) as session, pytest.raises(NoMasterResumeError):
        tailor_posting(
            session,
            posting_id,
            provider=FakeLLMProvider([]),
            renderer=SequencedPdfRenderer([1]),
            honesty_level="strict",
            theme="jakes-resume",
            renders_dir=tmp_path,
        )


def test_tailor_posting_wraps_output_error(db_engine: Engine, tmp_path: Path) -> None:
    posting_id = _seed_all(db_engine)
    provider = FakeLLMProvider([make_response(text="no json") for _ in range(4)])
    with session_scope(db_engine) as session, pytest.raises(TailoringOutputError):
        tailor_posting(
            session,
            posting_id,
            provider=provider,
            renderer=SequencedPdfRenderer([1]),
            honesty_level="strict",
            theme="jakes-resume",
            renders_dir=tmp_path,
        )
