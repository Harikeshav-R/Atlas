"""Tests for the ingest/reparse orchestration in :mod:`atlas.resume.service`."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytest

from atlas.db import session_scope
from atlas.resume.errors import MasterResumeNotFoundError
from atlas.resume.parser import parse_markdown
from atlas.resume.repository import get_blocks, get_latest_master_resume, list_versions
from atlas.resume.service import apply_reparse, apply_set, utcnow
from atlas.resume.structure import BlockType, ParsedBlock, ParsedResume

if TYPE_CHECKING:
    from sqlalchemy.engine import Engine

_CLOCK = datetime(2026, 8, 3, 9, 0, tzinfo=UTC)


def _fixed_clock() -> datetime:
    return _CLOCK


def test_utcnow_is_timezone_aware_utc() -> None:
    now = utcnow()
    assert now.tzinfo is UTC


def test_apply_set_first_creates_version_one(db_engine: Engine) -> None:
    with session_scope(db_engine) as session:
        outcome = apply_set(
            session,
            raw_markdown="## Skills\n\n- Python\n- Rust",
            source_path="/home/sam/resume.md",
            clock=_fixed_clock,
        )
    assert outcome.version == 1
    assert outcome.created is True
    assert outcome.block_count == 2
    with session_scope(db_engine) as session:
        latest = get_latest_master_resume(session)
        assert latest is not None
        assert latest.source_path == "/home/sam/resume.md"
        assert latest.created_at == _CLOCK


def test_apply_set_unchanged_content_is_noop(db_engine: Engine) -> None:
    markdown = "## Skills\n\n- Python"
    with session_scope(db_engine) as session:
        apply_set(session, raw_markdown=markdown, source_path="a.md", clock=_fixed_clock)
    # Re-set with only cosmetic (trailing-whitespace / blank-line) differences.
    with session_scope(db_engine) as session:
        outcome = apply_set(
            session,
            raw_markdown="## Skills\n\n- Python   \n\n",
            source_path="b.md",
            clock=_fixed_clock,
        )
    assert outcome.created is False
    assert outcome.version == 1
    assert outcome.block_count == 1
    with session_scope(db_engine) as session:
        # No second version was written, and the source path was not changed.
        assert [resume.version for resume in list_versions(session)] == [1]
        latest = get_latest_master_resume(session)
        assert latest is not None
        assert latest.source_path == "a.md"


def test_apply_set_changed_content_creates_next_version(db_engine: Engine) -> None:
    with session_scope(db_engine) as session:
        apply_set(
            session, raw_markdown="## Skills\n\n- Python", source_path=None, clock=_fixed_clock
        )
    with session_scope(db_engine) as session:
        outcome = apply_set(
            session,
            raw_markdown="## Skills\n\n- Python\n- Rust",
            source_path=None,
            clock=_fixed_clock,
        )
    assert outcome.version == 2
    assert outcome.created is True
    with session_scope(db_engine) as session:
        assert [resume.version for resume in list_versions(session)] == [1, 2]


def test_apply_set_uses_injected_parser(db_engine: Engine) -> None:
    sentinel = ParsedResume(
        blocks=[ParsedBlock(type=BlockType.OTHER, content_id="blk_x", position=0, text="ai")]
    )
    seen: list[str] = []

    def fake_parse(markdown: str) -> ParsedResume:
        seen.append(markdown)
        return sentinel

    with session_scope(db_engine) as session:
        outcome = apply_set(
            session,
            raw_markdown="raw source",
            source_path=None,
            parse=fake_parse,
            clock=_fixed_clock,
        )
        latest = get_latest_master_resume(session)
        assert latest is not None
        resume_id = latest.id
    assert seen == ["raw source"]
    assert outcome.block_count == 1
    assert resume_id is not None
    with session_scope(db_engine) as session:
        assert [block.text for block in get_blocks(session, resume_id)] == ["ai"]


def test_apply_reparse_without_resume_raises(db_engine: Engine) -> None:
    with session_scope(db_engine) as session, pytest.raises(MasterResumeNotFoundError):
        apply_reparse(session, clock=_fixed_clock)


def test_apply_reparse_creates_new_version_from_stored_source(db_engine: Engine) -> None:
    with session_scope(db_engine) as session:
        apply_set(
            session,
            raw_markdown="## Skills\n\n- Python",
            source_path="/home/sam/resume.md",
            clock=_fixed_clock,
        )
    calls: list[str] = []

    def spy_parse(markdown: str) -> ParsedResume:
        calls.append(markdown)
        return parse_markdown(markdown)

    with session_scope(db_engine) as session:
        outcome = apply_reparse(session, parse=spy_parse, clock=_fixed_clock)
    assert outcome.version == 2
    assert outcome.created is True
    # Reparse fed the stored source and carried the original source path forward.
    assert calls == ["## Skills\n\n- Python"]
    with session_scope(db_engine) as session:
        latest = get_latest_master_resume(session)
        assert latest is not None
        assert latest.source_path == "/home/sam/resume.md"
