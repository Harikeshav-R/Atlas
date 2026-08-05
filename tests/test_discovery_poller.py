"""Tests for the discovery poll in :mod:`atlas.discovery.poller`.

Pure over the in-memory ``db_engine`` fixture with a scripted ``FakeFetcher`` — no
scheduler or process involved (AGENTS.md §6.2).
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from atlas.db import session_scope
from atlas.db.models import JobSource
from atlas.discovery.poller import run_discovery_poll
from atlas.discovery.repository import get_ats_source, get_or_create_ats_source
from atlas.scrape.errors import FetchError
from atlas.scrape.fetcher import FetchResult
from atlas.scrape.repository import get_or_create_company, list_postings
from tests.conftest import FakeFetcher

if TYPE_CHECKING:
    from collections.abc import Mapping

    from sqlalchemy.engine import Engine

_POLLED = datetime(2026, 8, 4, 9, 0, tzinfo=UTC)


def _fixed_clock() -> datetime:
    return _POLLED


def _board(*ids: int) -> str:
    return json.dumps(
        {
            "jobs": [
                {
                    "id": job_id,
                    "title": f"Role {job_id}",
                    "absolute_url": f"https://boards.greenhouse.io/acme/jobs/{job_id}",
                    "location": {"name": "Remote"},
                    "content": "&lt;p&gt;Work.&lt;/p&gt;",
                }
                for job_id in ids
            ],
            "meta": {"total": len(ids)},
        }
    )


def _result(body: str) -> FetchResult:
    return FetchResult(
        url="https://boards-api.greenhouse.io/v1/boards/acme/jobs?content=true",
        status_code=200,
        content_type="application/json",
        body=body,
    )


def _watchlist(engine: Engine, *, ats_type: str = "greenhouse", board_token: str = "acme") -> None:
    with session_scope(engine) as session:
        company = get_or_create_company(session, name="Acme")
        assert company.id is not None
        get_or_create_ats_source(
            session, ats_type=ats_type, board_token=board_token, company_id=company.id
        )


def test_poll_discovers_and_persists(db_engine: Engine) -> None:
    _watchlist(db_engine)
    fetcher = FakeFetcher(_result(_board(1, 2)))
    with session_scope(db_engine) as session:
        outcome = run_discovery_poll(session, fetcher=fetcher, clock=_fixed_clock)
    assert outcome.sources_polled == 1
    assert outcome.discovered == 2
    assert outcome.skipped == 0
    assert outcome.failed_sources == 0
    with session_scope(db_engine) as session:
        postings = list_postings(session)
        assert {p.external_id for p in postings} == {"1", "2"}
        source = get_ats_source(session, ats_type="greenhouse", board_token="acme")
        assert source is not None
        assert source.last_polled_at == _POLLED


def test_poll_re_poll_is_a_no_op(db_engine: Engine) -> None:
    _watchlist(db_engine)
    with session_scope(db_engine) as session:
        run_discovery_poll(session, fetcher=FakeFetcher(_result(_board(1, 2))), clock=_fixed_clock)
    # A second poll of the same board discovers nothing new.
    with session_scope(db_engine) as session:
        outcome = run_discovery_poll(
            session, fetcher=FakeFetcher(_result(_board(1, 2))), clock=_fixed_clock
        )
    assert outcome.discovered == 0
    assert outcome.skipped == 2
    assert outcome.sources_polled == 1


def test_poll_best_effort_skips_a_failing_source(db_engine: Engine) -> None:
    # Two boards: the first fetch raises, the second succeeds. The failure is
    # counted and the good source is still polled.
    with session_scope(db_engine) as session:
        company = get_or_create_company(session, name="Acme")
        assert company.id is not None
        get_or_create_ats_source(
            session, ats_type="greenhouse", board_token="broken", company_id=company.id
        )
        get_or_create_ats_source(
            session, ats_type="greenhouse", board_token="acme", company_id=company.id
        )

    class _SequencedFetcher:
        def __init__(self) -> None:
            self.calls = 0

        def __call__(
            self,
            url: str,
            *,
            timeout_s: int,
            method: str = "GET",
            json_body: Mapping[str, Any] | None = None,
            headers: Mapping[str, str] | None = None,
        ) -> FetchResult:
            self.calls += 1
            if "broken" in url:
                raise FetchError("boom")
            return _result(_board(1))

    with session_scope(db_engine) as session:
        outcome = run_discovery_poll(session, fetcher=_SequencedFetcher(), clock=_fixed_clock)
    assert outcome.failed_sources == 1
    assert outcome.sources_polled == 1
    assert outcome.discovered == 1


def test_poll_skips_unknown_provider(db_engine: Engine) -> None:
    # A source whose provider has no adapter → UnknownAtsError (a DiscoveryError)
    # is caught and counted, never fetched. smartrecruiters is documented but not
    # yet registered (PROJECT.md §5.4-A).
    with session_scope(db_engine) as session:
        company = get_or_create_company(session, name="Acme")
        assert company.id is not None
        session.add(
            JobSource(
                type="ats",
                config={
                    "ats_type": "smartrecruiters",
                    "board_token": "acme",
                    "company_id": company.id,
                },
            )
        )
        session.flush()
    fetcher = FakeFetcher(_result(_board(1)))
    with session_scope(db_engine) as session:
        outcome = run_discovery_poll(session, fetcher=fetcher, clock=_fixed_clock)
    assert outcome.failed_sources == 1
    assert outcome.sources_polled == 0
    assert fetcher.calls == []


def test_poll_empty_watchlist_makes_no_fetch(db_engine: Engine) -> None:
    fetcher = FakeFetcher(_result(_board(1)))
    with session_scope(db_engine) as session:
        outcome = run_discovery_poll(session, fetcher=fetcher, clock=_fixed_clock)
    assert outcome.sources_polled == 0
    assert outcome.discovered == 0
    assert outcome.skipped == 0
    assert outcome.failed_sources == 0
    assert fetcher.calls == []
