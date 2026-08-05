"""Tests for the discovery persistence in :mod:`atlas.discovery.repository`."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from atlas.db import session_scope
from atlas.discovery.repository import (
    get_ats_source,
    get_or_create_ats_source,
    get_posting_by_source_external,
    list_enabled_ats_sources,
    stamp_last_polled_at,
)
from atlas.scrape.repository import (
    create_job_posting,
    get_or_create_company,
    get_or_create_url_source,
)

if TYPE_CHECKING:
    from sqlalchemy.engine import Engine

_POLLED = datetime(2026, 8, 4, 9, 0, tzinfo=UTC)
_FETCHED = datetime(2026, 8, 3, 12, 0, tzinfo=UTC)


def test_get_or_create_ats_source_dedups_by_type_and_token(db_engine: Engine) -> None:
    with session_scope(db_engine) as session:
        company = get_or_create_company(session, name="Acme")
        assert company.id is not None
        first = get_or_create_ats_source(
            session, ats_type="greenhouse", board_token="acme", company_id=company.id
        )
        first_id = first.id
        assert first.config == {
            "ats_type": "greenhouse",
            "board_token": "acme",
            "company_id": company.id,
        }
    with session_scope(db_engine) as session:
        company = get_or_create_company(session, name="Acme")
        assert company.id is not None
        again = get_or_create_ats_source(
            session, ats_type="greenhouse", board_token="acme", company_id=company.id
        )
        assert again.id == first_id
        other = get_or_create_ats_source(
            session, ats_type="greenhouse", board_token="globex", company_id=company.id
        )
        assert other.id != first_id


def test_get_ats_source_hit_and_miss(db_engine: Engine) -> None:
    with session_scope(db_engine) as session:
        company = get_or_create_company(session, name="Acme")
        assert company.id is not None
        get_or_create_ats_source(
            session, ats_type="greenhouse", board_token="acme", company_id=company.id
        )
    with session_scope(db_engine) as session:
        assert get_ats_source(session, ats_type="greenhouse", board_token="acme") is not None
        assert get_ats_source(session, ats_type="greenhouse", board_token="nope") is None


def test_list_enabled_ats_sources_excludes_disabled_and_url(db_engine: Engine) -> None:
    with session_scope(db_engine) as session:
        company = get_or_create_company(session, name="Acme")
        assert company.id is not None
        # The shared url source must never appear.
        get_or_create_url_source(session)
        enabled = get_or_create_ats_source(
            session, ats_type="greenhouse", board_token="acme", company_id=company.id
        )
        disabled = get_or_create_ats_source(
            session, ats_type="greenhouse", board_token="globex", company_id=company.id
        )
        disabled.enabled = False
        session.add(disabled)
        session.flush()
        enabled_id = enabled.id
    with session_scope(db_engine) as session:
        sources = list_enabled_ats_sources(session)
        assert [s.id for s in sources] == [enabled_id]


def test_stamp_last_polled_at(db_engine: Engine) -> None:
    with session_scope(db_engine) as session:
        company = get_or_create_company(session, name="Acme")
        assert company.id is not None
        source = get_or_create_ats_source(
            session, ats_type="greenhouse", board_token="acme", company_id=company.id
        )
        assert source.last_polled_at is None
        stamp_last_polled_at(session, source, _POLLED)
    with session_scope(db_engine) as session:
        reloaded = get_ats_source(session, ats_type="greenhouse", board_token="acme")
        assert reloaded is not None
        assert reloaded.last_polled_at == _POLLED


def test_get_posting_by_source_external_hit_and_miss(db_engine: Engine) -> None:
    with session_scope(db_engine) as session:
        company = get_or_create_company(session, name="Acme")
        source = get_or_create_url_source(session)
        assert company.id is not None
        assert source.id is not None
        create_job_posting(
            session,
            source_id=source.id,
            company_id=company.id,
            title="Backend Engineer",
            apply_url="https://x.test/1",
            dedupe_hash="h1",
            fetched_at=_FETCHED,
            external_id="ext-1",
        )
        source_id = source.id
    with session_scope(db_engine) as session:
        assert (
            get_posting_by_source_external(session, source_id=source_id, external_id="ext-1")
            is not None
        )
        assert (
            get_posting_by_source_external(session, source_id=source_id, external_id="nope") is None
        )
