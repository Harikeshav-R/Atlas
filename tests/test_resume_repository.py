"""Tests for master-resume persistence in :mod:`atlas.resume.repository`."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytest

from atlas.db import session_scope
from atlas.resume.errors import MasterResumeNotFoundError
from atlas.resume.parser import parse_markdown
from atlas.resume.repository import (
    create_version,
    get_blocks,
    get_latest_master_resume,
    get_master_resume,
    list_versions,
)
from atlas.resume.structure import BlockType, ParsedBlock, ParsedResume

if TYPE_CHECKING:
    from sqlalchemy.engine import Engine

_CREATED = datetime(2026, 8, 3, 12, 0, tzinfo=UTC)


def _make_version(engine: Engine, markdown: str, *, source_path: str | None = None) -> int:
    """Create a version from ``markdown`` and return its version number."""
    with session_scope(engine) as session:
        resume = create_version(
            session,
            raw_markdown=markdown,
            source_path=source_path,
            parsed=parse_markdown(markdown),
            created_at=_CREATED,
        )
        return resume.version


def test_get_latest_none_when_empty(db_engine: Engine) -> None:
    with session_scope(db_engine) as session:
        assert get_latest_master_resume(session) is None


def test_create_version_starts_at_one_and_persists_blocks(db_engine: Engine) -> None:
    markdown = "# Sam\n\n## Skills\n\n- Python\n- Rust"
    with session_scope(db_engine) as session:
        resume = create_version(
            session,
            raw_markdown=markdown,
            source_path="/home/sam/resume.md",
            parsed=parse_markdown(markdown),
            created_at=_CREATED,
        )
        assert resume.version == 1
        resume_id = resume.id
    with session_scope(db_engine) as session:
        latest = get_latest_master_resume(session)
        assert latest is not None
        assert latest.version == 1
        assert latest.source_path == "/home/sam/resume.md"
        assert latest.created_at == _CREATED
        blocks = get_blocks(session, resume_id)  # type: ignore[arg-type]
        assert [block.text for block in blocks] == ["Sam", "Python", "Rust"]
        assert [block.type for block in blocks] == ["contact", "skill", "skill"]
        assert [block.position for block in blocks] == [0, 1, 2]


def test_create_version_increments_and_leaves_earlier_versions_untouched(
    db_engine: Engine,
) -> None:
    first_id = None
    with session_scope(db_engine) as session:
        first = create_version(
            session,
            raw_markdown="## Skills\n\n- Python",
            source_path=None,
            parsed=parse_markdown("## Skills\n\n- Python"),
            created_at=_CREATED,
        )
        first_id = first.id
    with session_scope(db_engine) as session:
        second = create_version(
            session,
            raw_markdown="## Skills\n\n- Python\n- Rust",
            source_path=None,
            parsed=parse_markdown("## Skills\n\n- Python\n- Rust"),
            created_at=_CREATED,
        )
        assert second.version == 2
    with session_scope(db_engine) as session:
        # v1's blocks are unchanged (immutability): still a single Python block.
        assert [block.text for block in get_blocks(session, first_id)] == ["Python"]  # type: ignore[arg-type]
        assert len(list_versions(session)) == 2


def test_tags_round_trip(db_engine: Engine) -> None:
    parsed = ParsedResume(
        blocks=[
            ParsedBlock(
                type=BlockType.EXPERIENCE,
                content_id="blk_abc123456789",
                position=0,
                text="Shipped it",
                tags={"metrics": ["30%"]},
            )
        ]
    )
    resume_id = None
    with session_scope(db_engine) as session:
        resume = create_version(
            session,
            raw_markdown="raw",
            source_path=None,
            parsed=parsed,
            created_at=_CREATED,
        )
        resume_id = resume.id
    with session_scope(db_engine) as session:
        block = get_blocks(session, resume_id)[0]  # type: ignore[arg-type]
        assert block.tags == {"metrics": ["30%"]}


def test_get_master_resume_by_version(db_engine: Engine) -> None:
    _make_version(db_engine, "## Skills\n\n- Python")
    _make_version(db_engine, "## Skills\n\n- Rust")
    with session_scope(db_engine) as session:
        assert get_master_resume(session, 2).raw_markdown == "## Skills\n\n- Rust"


def test_get_master_resume_missing_raises(db_engine: Engine) -> None:
    with session_scope(db_engine) as session, pytest.raises(MasterResumeNotFoundError):
        get_master_resume(session, 99)


def test_list_versions_ordered_ascending(db_engine: Engine) -> None:
    _make_version(db_engine, "## Skills\n\n- Python")
    _make_version(db_engine, "## Skills\n\n- Rust")
    with session_scope(db_engine) as session:
        assert [resume.version for resume in list_versions(session)] == [1, 2]
