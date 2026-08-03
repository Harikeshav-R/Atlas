"""Tests for the render orchestration in :mod:`atlas.render.service`."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytest

from atlas.db import session_scope
from atlas.profiles.repository import upsert_user
from atlas.render.errors import NoMasterResumeError
from atlas.render.service import render_master_resume
from atlas.resume.repository import create_version
from atlas.resume.structure import BlockType, ParsedBlock, ParsedResume
from tests.conftest import FakePdfRenderer

if TYPE_CHECKING:
    from pathlib import Path

    from sqlalchemy.engine import Engine

_CREATED = datetime(2026, 8, 3, tzinfo=UTC)


def _seed_resume(engine: Engine, *, text: str = "Senior backend engineer.") -> None:
    with session_scope(engine) as session:
        parsed = ParsedResume(
            blocks=[ParsedBlock(type=BlockType.SUMMARY, content_id="blk_1", position=0, text=text)]
        )
        create_version(
            session,
            raw_markdown="# Sam",
            source_path="/home/sam/resume.md",
            parsed=parsed,
            created_at=_CREATED,
        )


def test_render_master_resume_writes_pdf_and_reports_one_page(
    db_engine: Engine, tmp_path: Path
) -> None:
    _seed_resume(db_engine, text="Distributed systems and reliability.")
    with session_scope(db_engine) as session:
        upsert_user(session, name="Sam Lee")
    renderer = FakePdfRenderer(page_count=1)
    with session_scope(db_engine) as session:
        outcome = render_master_resume(
            session, renderer=renderer, theme="jakes-resume", renders_dir=tmp_path
        )
    assert outcome.one_page is True
    assert outcome.page_count == 1
    assert outcome.version == 1
    assert outcome.theme == "jakes-resume"
    # The PDF was written under the injected dir with a name-derived, versioned stem.
    assert outcome.path == str(tmp_path / "Sam_Lee__resume__v1.pdf")
    assert (tmp_path / "Sam_Lee__resume__v1.pdf").read_bytes() == b"%PDF-fake"
    # The renderer received HTML carrying the resume content.
    assert "Distributed systems and reliability." in renderer.html_calls[0]


def test_render_master_resume_flags_overflow(db_engine: Engine, tmp_path: Path) -> None:
    _seed_resume(db_engine)
    with session_scope(db_engine) as session:
        upsert_user(session, name="Sam")
    renderer = FakePdfRenderer(page_count=2)
    with session_scope(db_engine) as session:
        outcome = render_master_resume(
            session, renderer=renderer, theme="jakes-resume", renders_dir=tmp_path
        )
    assert outcome.page_count == 2
    assert outcome.one_page is False


def test_render_master_resume_uses_default_name_without_user(
    db_engine: Engine, tmp_path: Path
) -> None:
    # No user row (onboarding not run) → the default name/slug is used.
    _seed_resume(db_engine)
    renderer = FakePdfRenderer(page_count=1)
    with session_scope(db_engine) as session:
        outcome = render_master_resume(
            session, renderer=renderer, theme="jakes-resume", renders_dir=tmp_path
        )
    assert outcome.path == str(tmp_path / "Resume__resume__v1.pdf")


def test_render_master_resume_slug_falls_back_for_symbol_only_name(
    db_engine: Engine, tmp_path: Path
) -> None:
    # A name with no slug-able characters falls back to the default stem.
    _seed_resume(db_engine)
    with session_scope(db_engine) as session:
        upsert_user(session, name="!!!")
    renderer = FakePdfRenderer(page_count=1)
    with session_scope(db_engine) as session:
        outcome = render_master_resume(
            session, renderer=renderer, theme="jakes-resume", renders_dir=tmp_path
        )
    assert outcome.path == str(tmp_path / "resume__resume__v1.pdf")


def test_render_master_resume_without_resume_raises(db_engine: Engine, tmp_path: Path) -> None:
    renderer = FakePdfRenderer()
    with session_scope(db_engine) as session, pytest.raises(NoMasterResumeError):
        render_master_resume(session, renderer=renderer, theme="jakes-resume", renders_dir=tmp_path)
