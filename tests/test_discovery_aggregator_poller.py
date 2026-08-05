"""Tests for the aggregator poll in :mod:`atlas.discovery.poller`.

Pure over the in-memory ``db_engine`` fixture with a scripted ``FakeFetcher`` — no
scheduler or process involved (AGENTS.md §6.2). Mirrors ``test_discovery_poller``
but for :func:`run_aggregator_poll` (RemoteOK feed, per-posting companies).
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from atlas.db import session_scope
from atlas.db.models import JobSource
from atlas.discovery.aggregators.structure import SavedSearch
from atlas.discovery.poller import run_aggregator_poll
from atlas.discovery.repository import (
    get_aggregator_source,
    get_or_create_aggregator_source,
)
from atlas.profiles.preferences import ProfilePreferences
from atlas.profiles.repository import create_profile
from atlas.scrape.errors import FetchError
from atlas.scrape.fetcher import FetchResult
from atlas.scrape.repository import list_postings
from tests.conftest import FakeFetcher

if TYPE_CHECKING:
    from collections.abc import Mapping

    from sqlalchemy.engine import Engine

_POLLED = datetime(2026, 8, 4, 9, 0, tzinfo=UTC)


def _fixed_clock() -> datetime:
    return _POLLED


def _profile(engine: Engine) -> int:
    """Create an active profile and return its id (the saved-search FK target)."""
    with session_scope(engine) as session:
        profile = create_profile(session, name="Backend", preferences=ProfilePreferences())
        assert profile.id is not None
        return profile.id


def _feed(*ids: int) -> str:
    return json.dumps(
        [
            {"legal": "notice"},
            *[
                {
                    "id": job_id,
                    "company": f"Company {job_id}",
                    "position": f"Engineer {job_id}",
                    "url": f"https://remoteok.com/remote-jobs/{job_id}",
                    "tags": ["python"],
                    "description": "Work.",
                }
                for job_id in ids
            ],
        ]
    )


def _result(body: str) -> FetchResult:
    return FetchResult(
        url="https://remoteok.com/api",
        status_code=200,
        content_type="application/json",
        body=body,
    )


def _saved_search(
    engine: Engine, profile_id: int, *, aggregator: str = "remoteok", query: str = "python"
) -> None:
    with session_scope(engine) as session:
        get_or_create_aggregator_source(
            session,
            aggregator=aggregator,
            spec=SavedSearch(query=query),
            profile_id=profile_id,
        )


def test_poll_discovers_and_persists(db_engine: Engine) -> None:
    profile_id = _profile(db_engine)
    _saved_search(db_engine, profile_id)
    fetcher = FakeFetcher(_result(_feed(1, 2)))
    with session_scope(db_engine) as session:
        outcome = run_aggregator_poll(session, fetcher=fetcher, clock=_fixed_clock)
    assert outcome.sources_polled == 1
    assert outcome.discovered == 2
    assert outcome.skipped == 0
    assert outcome.failed_sources == 0
    with session_scope(db_engine) as session:
        postings = list_postings(session)
        assert {p.external_id for p in postings} == {"1", "2"}
        # Each posting get-or-created its own company (aggregators span many).
        assert len({p.company_id for p in postings}) == 2
        source = get_aggregator_source(
            session, aggregator="remoteok", spec=SavedSearch(query="python"), profile_id=profile_id
        )
        assert source is not None
        assert source.last_polled_at == _POLLED
    assert fetcher.calls[0].url == "https://remoteok.com/api"


def test_poll_falls_back_to_placeholder_company(db_engine: Engine) -> None:
    _saved_search(db_engine, _profile(db_engine))
    feed = json.dumps(
        [
            {
                "id": 7,
                "position": "Engineer",
                "url": "https://remoteok.com/remote-jobs/7",
                "tags": ["python"],
                "description": "Work.",
            }
        ]
    )
    with session_scope(db_engine) as session:
        run_aggregator_poll(session, fetcher=FakeFetcher(_result(feed)), clock=_fixed_clock)
    with session_scope(db_engine) as session:
        from atlas.db.models import Company

        postings = list_postings(session)
        assert len(postings) == 1
        company = session.get(Company, postings[0].company_id)
        assert company is not None
        assert company.name == "Unknown company"


def test_poll_re_poll_is_a_no_op(db_engine: Engine) -> None:
    _saved_search(db_engine, _profile(db_engine))
    with session_scope(db_engine) as session:
        run_aggregator_poll(session, fetcher=FakeFetcher(_result(_feed(1, 2))), clock=_fixed_clock)
    with session_scope(db_engine) as session:
        outcome = run_aggregator_poll(
            session, fetcher=FakeFetcher(_result(_feed(1, 2))), clock=_fixed_clock
        )
    assert outcome.discovered == 0
    assert outcome.skipped == 2
    assert outcome.sources_polled == 1


def test_poll_best_effort_skips_a_failing_source(db_engine: Engine) -> None:
    # Two searches on two providers: the RemoteOK fetch raises, the Remotive one
    # succeeds. The failure is counted and the good source is still polled.
    profile_id = _profile(db_engine)
    with session_scope(db_engine) as session:
        get_or_create_aggregator_source(
            session, aggregator="remoteok", spec=SavedSearch(query="python"), profile_id=profile_id
        )
        get_or_create_aggregator_source(
            session,
            aggregator="remotive",
            spec=SavedSearch(query="python"),
            profile_id=profile_id,
        )

    class _SequencedFetcher:
        def __call__(
            self,
            url: str,
            *,
            timeout_s: int,
            method: str = "GET",
            json_body: Mapping[str, Any] | None = None,
            headers: Mapping[str, str] | None = None,
        ) -> FetchResult:
            if "remoteok" in url:
                raise FetchError("boom")
            return FetchResult(
                url=url,
                status_code=200,
                content_type="application/json",
                body=json.dumps(
                    {
                        "jobs": [
                            {
                                "id": 5,
                                "company_name": "Globex",
                                "title": "Python Engineer",
                                "url": "https://remotive.com/remote-jobs/5",
                            }
                        ]
                    }
                ),
            )

    with session_scope(db_engine) as session:
        outcome = run_aggregator_poll(session, fetcher=_SequencedFetcher(), clock=_fixed_clock)
    assert outcome.failed_sources == 1
    assert outcome.sources_polled == 1
    assert outcome.discovered == 1


def test_poll_skips_unknown_provider(db_engine: Engine) -> None:
    # A source whose provider has no adapter → UnknownAggregatorError (a
    # DiscoveryError) is caught and counted, never fetched.
    profile_id = _profile(db_engine)
    with session_scope(db_engine) as session:
        session.add(
            JobSource(
                type="aggregator",
                config={"aggregator": "linkedin", "search": {"query": "python"}},
                profile_id=profile_id,
            )
        )
        session.flush()
    fetcher = FakeFetcher(_result(_feed(1)))
    with session_scope(db_engine) as session:
        outcome = run_aggregator_poll(session, fetcher=fetcher, clock=_fixed_clock)
    assert outcome.failed_sources == 1
    assert outcome.sources_polled == 0
    assert fetcher.calls == []


def test_poll_empty_watchlist_makes_no_fetch(db_engine: Engine) -> None:
    fetcher = FakeFetcher(_result(_feed(1)))
    with session_scope(db_engine) as session:
        outcome = run_aggregator_poll(session, fetcher=fetcher, clock=_fixed_clock)
    assert outcome.sources_polled == 0
    assert outcome.discovered == 0
    assert outcome.skipped == 0
    assert outcome.failed_sources == 0
    assert fetcher.calls == []
