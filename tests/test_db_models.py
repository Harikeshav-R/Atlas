"""Tests for the SQLModel tables in :mod:`atlas.db.models`."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlmodel import col, select

from atlas.db import MasterResume, Profile, ResumeBlock, User, session_scope

if TYPE_CHECKING:
    from sqlalchemy.engine import Engine


def test_user_defaults() -> None:
    user = User(name="Sam")
    assert user.id is None
    assert user.email is None
    assert user.settings == {}


def test_profile_defaults() -> None:
    profile = Profile(name="Backend Engineer")
    assert profile.id is None
    assert profile.preferences == {}
    assert profile.tailoring_emphasis == []
    assert profile.match_criteria == {}
    assert profile.active is True


def test_user_json_and_columns_round_trip(db_engine: Engine) -> None:
    with session_scope(db_engine) as session:
        session.add(User(name="Sam", email="sam@example.com", settings={"theme": "dark"}))
    # Read (and assert) inside a fresh scope, before its commit-at-exit expires
    # the instance and detaches it.
    with session_scope(db_engine) as session:
        stored = session.exec(select(User)).one()
        assert stored.id is not None
        assert stored.name == "Sam"
        assert stored.email == "sam@example.com"
        assert stored.settings == {"theme": "dark"}


def test_profile_json_columns_round_trip(db_engine: Engine) -> None:
    with session_scope(db_engine) as session:
        session.add(
            Profile(
                name="ML Engineer",
                preferences={"remote": True},
                tailoring_emphasis=["distributed systems", "product sense"],
                match_criteria={"min_salary": 150000},
                active=False,
            )
        )
    with session_scope(db_engine) as session:
        stored = session.exec(select(Profile)).one()
        assert stored.preferences == {"remote": True}
        assert stored.tailoring_emphasis == ["distributed systems", "product sense"]
        assert stored.match_criteria == {"min_salary": 150000}
        assert stored.active is False


def test_master_resume_defaults() -> None:
    created = datetime(2026, 8, 3, tzinfo=UTC)
    resume = MasterResume(version=1, raw_markdown="# Sam", created_at=created)
    assert resume.id is None
    assert resume.source_path is None
    assert resume.parsed == {}
    assert resume.created_at == created


def test_resume_block_defaults() -> None:
    block = ResumeBlock(
        master_resume_id=1,
        type="experience",
        content_id="blk_abc123",
        position=0,
        text="Shipped a thing",
    )
    assert block.id is None
    assert block.tags == {}


def test_master_resume_and_blocks_round_trip(db_engine: Engine) -> None:
    created = datetime(2026, 8, 3, 12, 30, tzinfo=UTC)
    with session_scope(db_engine) as session:
        resume = MasterResume(
            version=1,
            source_path="/home/sam/resume.md",
            raw_markdown="# Sam\n\n## Experience\n\n- Shipped a thing",
            parsed={"blocks": [{"type": "experience", "text": "Shipped a thing"}]},
            created_at=created,
        )
        session.add(resume)
        session.flush()
        assert resume.id is not None
        session.add(
            ResumeBlock(
                master_resume_id=resume.id,
                type="experience",
                content_id="blk_abc123",
                position=0,
                text="Shipped a thing",
                tags={"metrics": ["30% faster"]},
            )
        )
    with session_scope(db_engine) as session:
        stored = session.exec(select(MasterResume)).one()
        assert stored.version == 1
        assert stored.source_path == "/home/sam/resume.md"
        assert stored.parsed == {"blocks": [{"type": "experience", "text": "Shipped a thing"}]}
        # UtcDateTime re-attaches UTC on load (SQLite would otherwise drop tzinfo).
        assert stored.created_at == created
        assert stored.created_at.tzinfo is UTC
        block = session.exec(select(ResumeBlock).order_by(col(ResumeBlock.position))).one()
        assert block.master_resume_id == stored.id
        assert block.content_id == "blk_abc123"
        assert block.tags == {"metrics": ["30% faster"]}
