"""Tests for job-posting persistence in :mod:`atlas.scrape.repository`."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytest

from atlas.db import session_scope
from atlas.scrape.errors import JobPostingNotFoundError
from atlas.scrape.repository import (
    URL_SOURCE_TYPE,
    create_job_posting,
    get_or_create_company,
    get_or_create_url_source,
    get_posting,
    get_posting_by_dedupe,
    list_postings,
)

if TYPE_CHECKING:
    from sqlalchemy.engine import Engine

_FETCHED = datetime(2026, 8, 3, 12, 0, tzinfo=UTC)


def test_get_or_create_company_dedups_by_name(db_engine: Engine) -> None:
    with session_scope(db_engine) as session:
        first = get_or_create_company(session, name="Acme")
        first_id = first.id
    with session_scope(db_engine) as session:
        again = get_or_create_company(session, name="Acme")
        assert again.id == first_id
        other = get_or_create_company(session, name="Globex")
        assert other.id != first_id


def test_get_or_create_url_source_is_singular(db_engine: Engine) -> None:
    with session_scope(db_engine) as session:
        first = get_or_create_url_source(session)
        assert first.type == URL_SOURCE_TYPE
        first_id = first.id
    with session_scope(db_engine) as session:
        again = get_or_create_url_source(session)
        assert again.id == first_id


def _seed_posting(engine: Engine, *, dedupe: str = "hash1", title: str = "Role") -> int:
    with session_scope(engine) as session:
        company = get_or_create_company(session, name="Acme")
        source = get_or_create_url_source(session)
        assert company.id is not None
        assert source.id is not None
        posting = create_job_posting(
            session,
            source_id=source.id,
            company_id=company.id,
            title=title,
            apply_url="https://jobs.acme.test/1",
            dedupe_hash=dedupe,
            fetched_at=_FETCHED,
            salary={"min": 100000},
            requirements={"must": ["Python"]},
            keywords=["python"],
            raw_snapshot_ref="snapshots/hash1.html",
        )
        assert posting.id is not None
        return posting.id


def test_create_and_get_posting(db_engine: Engine) -> None:
    posting_id = _seed_posting(db_engine)
    with session_scope(db_engine) as session:
        stored = get_posting(session, posting_id)
        assert stored.title == "Role"
        assert stored.salary == {"min": 100000}
        assert stored.requirements == {"must": ["Python"]}
        assert stored.keywords == ["python"]
        assert stored.fetched_at == _FETCHED
        assert stored.fetched_at.tzinfo is UTC


def test_get_posting_missing_raises(db_engine: Engine) -> None:
    with session_scope(db_engine) as session, pytest.raises(JobPostingNotFoundError):
        get_posting(session, 999)


def test_get_posting_by_dedupe_hit_and_miss(db_engine: Engine) -> None:
    _seed_posting(db_engine, dedupe="known")
    with session_scope(db_engine) as session:
        assert get_posting_by_dedupe(session, "known") is not None
        assert get_posting_by_dedupe(session, "unknown") is None


def test_list_postings_in_insertion_order(db_engine: Engine) -> None:
    _seed_posting(db_engine, dedupe="a", title="First")
    _seed_posting(db_engine, dedupe="b", title="Second")
    with session_scope(db_engine) as session:
        assert [p.title for p in list_postings(session)] == ["First", "Second"]
