"""Tests for the SQLModel tables in :mod:`atlas.db.models`."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlmodel import col, select

from atlas.db import (
    Company,
    JobPosting,
    JobSource,
    MasterResume,
    Profile,
    ResumeBlock,
    User,
    session_scope,
)

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


def test_company_defaults() -> None:
    company = Company(name="Acme")
    assert company.id is None
    assert company.ats_type is None
    assert company.domain is None
    assert company.notes is None


def test_job_source_defaults() -> None:
    source = JobSource(type="url")
    assert source.id is None
    assert source.config == {}
    assert source.profile_id is None
    assert source.enabled is True
    assert source.last_polled_at is None


def test_job_posting_defaults() -> None:
    posting = JobPosting(
        source_id=1,
        company_id=1,
        title="Backend Engineer",
        apply_url="https://jobs.example.com/1",
        fetched_at=datetime(2026, 8, 3, tzinfo=UTC),
        dedupe_hash="abc",
    )
    assert posting.id is None
    assert posting.salary == {}
    assert posting.requirements == {}
    assert posting.keywords == []
    assert posting.description == ""
    assert posting.posted_at is None
    assert posting.raw_snapshot_ref is None


def test_job_posting_round_trip_with_fks(db_engine: Engine) -> None:
    fetched = datetime(2026, 8, 3, 15, 45, tzinfo=UTC)
    with session_scope(db_engine) as session:
        company = Company(name="Acme", domain="acme.test")
        source = JobSource(type="url")
        session.add(company)
        session.add(source)
        session.flush()
        assert company.id is not None
        assert source.id is not None
        session.add(
            JobPosting(
                source_id=source.id,
                company_id=company.id,
                title="Senior Backend Engineer",
                location="Remote (US)",
                remote_type="remote",
                salary={"min": 150000, "currency": "USD"},
                description="Build things.",
                requirements={"must": ["Python"], "nice": ["Rust"]},
                keywords=["python", "postgres"],
                apply_url="https://jobs.acme.test/senior-backend",
                posted_at=fetched,
                raw_snapshot_ref="snapshots/abc123.html",
                fetched_at=fetched,
                dedupe_hash="abc123",
            )
        )
    with session_scope(db_engine) as session:
        stored = session.exec(select(JobPosting)).one()
        company = session.exec(select(Company)).one()
        source = session.exec(select(JobSource)).one()
        assert stored.company_id == company.id
        assert stored.source_id == source.id
        assert stored.salary == {"min": 150000, "currency": "USD"}
        assert stored.requirements == {"must": ["Python"], "nice": ["Rust"]}
        assert stored.keywords == ["python", "postgres"]
        assert stored.raw_snapshot_ref == "snapshots/abc123.html"
        # UtcDateTime re-attaches UTC on load for both timestamp columns.
        assert stored.fetched_at == fetched
        assert stored.fetched_at.tzinfo is UTC
        assert stored.posted_at == fetched
        assert stored.posted_at is not None
        assert stored.posted_at.tzinfo is UTC
