"""Tests for the discovery orchestration in :mod:`atlas.discovery.service`."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from atlas.db import session_scope
from atlas.db.models import Company
from atlas.discovery.aggregators.structure import SavedSearch
from atlas.discovery.repository import (
    get_aggregator_source,
    get_ats_source,
    get_or_create_aggregator_source,
    get_or_create_ats_source,
)
from atlas.discovery.service import (
    add_saved_search,
    add_watchlist_company,
    persist_aggregated,
    persist_discovered,
)
from atlas.discovery.structure import DiscoveredPosting
from atlas.profiles.preferences import ProfilePreferences
from atlas.profiles.repository import create_profile
from atlas.scrape.repository import get_or_create_company, list_postings
from atlas.scrape.service import dedupe_hash_for
from atlas.scrape.structure import ScrapedPosting

if TYPE_CHECKING:
    from sqlalchemy.engine import Engine

_FETCHED = datetime(2026, 8, 4, 9, 0, tzinfo=UTC)


def _fixed_clock() -> datetime:
    return _FETCHED


def _discovered(external_id: str, apply_url: str, *, title: str = "Engineer") -> DiscoveredPosting:
    return DiscoveredPosting(
        external_id=external_id,
        posting=ScrapedPosting(title=title, apply_url=apply_url),
    )


def _aggregated(
    external_id: str, apply_url: str, *, company: str = "Acme", title: str = "Engineer"
) -> DiscoveredPosting:
    return DiscoveredPosting(
        external_id=external_id,
        posting=ScrapedPosting(title=title, company=company, apply_url=apply_url),
    )


def _profile(engine: Engine) -> int:
    with session_scope(engine) as session:
        profile = create_profile(session, name="Backend", preferences=ProfilePreferences())
        assert profile.id is not None
        return profile.id


def test_add_watchlist_company_creates_company_and_source(db_engine: Engine) -> None:
    with session_scope(db_engine) as session:
        outcome = add_watchlist_company(
            session,
            name="Acme",
            ats_type="greenhouse",
            board_token="acme",
            domain="boards.greenhouse.io",
        )
        assert outcome.created is True
        assert outcome.name == "Acme"
        assert outcome.ats_type == "greenhouse"
        assert outcome.board_token == "acme"
    with session_scope(db_engine) as session:
        company = session.get(Company, outcome.company_id)
        assert company is not None
        assert company.ats_type == "greenhouse"
        assert company.ats_board_ref == "acme"
        assert company.domain == "boards.greenhouse.io"
        assert get_ats_source(session, ats_type="greenhouse", board_token="acme") is not None


def test_add_watchlist_company_is_idempotent(db_engine: Engine) -> None:
    with session_scope(db_engine) as session:
        first = add_watchlist_company(
            session, name="Acme", ats_type="greenhouse", board_token="acme"
        )
    with session_scope(db_engine) as session:
        again = add_watchlist_company(
            session, name="Acme", ats_type="greenhouse", board_token="acme"
        )
        assert again.created is False
        assert again.source_id == first.source_id
        assert again.company_id == first.company_id


def test_persist_discovered_inserts_new_postings(db_engine: Engine) -> None:
    with session_scope(db_engine) as session:
        company = get_or_create_company(session, name="Acme")
        assert company.id is not None
        source = get_or_create_ats_source(
            session, ats_type="greenhouse", board_token="acme", company_id=company.id
        )
        outcome = persist_discovered(
            session,
            source=source,
            company_id=company.id,
            discovered=[
                _discovered("1", "https://x.test/1"),
                _discovered("2", "https://x.test/2"),
            ],
            clock=_fixed_clock,
        )
        assert outcome.discovered == 2
        assert outcome.skipped == 0
    with session_scope(db_engine) as session:
        postings = list_postings(session)
        assert {p.external_id for p in postings} == {"1", "2"}
        assert all(p.fetched_at == _FETCHED for p in postings)


def test_persist_discovered_skips_existing_external_id(db_engine: Engine) -> None:
    with session_scope(db_engine) as session:
        company = get_or_create_company(session, name="Acme")
        assert company.id is not None
        source = get_or_create_ats_source(
            session, ats_type="greenhouse", board_token="acme", company_id=company.id
        )
        persist_discovered(
            session,
            source=source,
            company_id=company.id,
            discovered=[_discovered("1", "https://x.test/1")],
            clock=_fixed_clock,
        )
    with session_scope(db_engine) as session:
        reloaded = get_ats_source(session, ats_type="greenhouse", board_token="acme")
        assert reloaded is not None and reloaded.id is not None
        company = get_or_create_company(session, name="Acme")
        assert company.id is not None
        # Same external id → skipped (a re-poll no-op).
        outcome = persist_discovered(
            session,
            source=reloaded,
            company_id=company.id,
            discovered=[_discovered("1", "https://x.test/1")],
            clock=_fixed_clock,
        )
        assert outcome.discovered == 0
        assert outcome.skipped == 1


def test_persist_discovered_skips_cross_source_dedupe_hash(db_engine: Engine) -> None:
    # A posting whose normalized apply URL already exists (e.g. pasted via atlas add)
    # is skipped even under a different external id.
    from atlas.scrape.repository import create_job_posting, get_or_create_url_source

    with session_scope(db_engine) as session:
        company = get_or_create_company(session, name="Acme")
        url_source = get_or_create_url_source(session)
        assert company.id is not None and url_source.id is not None
        create_job_posting(
            session,
            source_id=url_source.id,
            company_id=company.id,
            title="Engineer",
            apply_url="https://x.test/shared",
            dedupe_hash=dedupe_hash_for("https://x.test/shared"),
            fetched_at=_FETCHED,
        )
        ats_source = get_or_create_ats_source(
            session, ats_type="greenhouse", board_token="acme", company_id=company.id
        )
        outcome = persist_discovered(
            session,
            source=ats_source,
            company_id=company.id,
            discovered=[_discovered("gh-1", "https://x.test/shared/")],
            clock=_fixed_clock,
        )
        assert outcome.discovered == 0
        assert outcome.skipped == 1


def test_add_saved_search_creates_source(db_engine: Engine) -> None:
    profile_id = _profile(db_engine)
    with session_scope(db_engine) as session:
        outcome = add_saved_search(
            session,
            aggregator="remoteok",
            spec=SavedSearch(query="python backend", location="remote"),
            profile_id=profile_id,
        )
        assert outcome.created is True
        assert outcome.aggregator == "remoteok"
        assert outcome.query == "python backend"
        assert outcome.profile_id == profile_id
    with session_scope(db_engine) as session:
        source = get_aggregator_source(
            session,
            aggregator="remoteok",
            spec=SavedSearch(query="python backend", location="remote"),
            profile_id=profile_id,
        )
        assert source is not None
        assert source.config["aggregator"] == "remoteok"


def test_add_saved_search_is_idempotent(db_engine: Engine) -> None:
    profile_id = _profile(db_engine)
    with session_scope(db_engine) as session:
        first = add_saved_search(
            session, aggregator="remoteok", spec=SavedSearch(query="python"), profile_id=profile_id
        )
    with session_scope(db_engine) as session:
        again = add_saved_search(
            session, aggregator="remoteok", spec=SavedSearch(query="python"), profile_id=profile_id
        )
        assert again.created is False
        assert again.source_id == first.source_id


def test_persist_aggregated_creates_a_company_per_posting(db_engine: Engine) -> None:
    profile_id = _profile(db_engine)
    with session_scope(db_engine) as session:
        source = get_or_create_aggregator_source(
            session, aggregator="remoteok", spec=SavedSearch(query="python"), profile_id=profile_id
        )
        outcome = persist_aggregated(
            session,
            source=source,
            discovered=[
                _aggregated("1", "https://x.test/1", company="Acme"),
                _aggregated("2", "https://x.test/2", company="Globex"),
            ],
            clock=_fixed_clock,
        )
        assert outcome.discovered == 2
    with session_scope(db_engine) as session:
        postings = list_postings(session)
        assert {p.external_id for p in postings} == {"1", "2"}
        assert len({p.company_id for p in postings}) == 2


def test_persist_aggregated_falls_back_to_placeholder_company(db_engine: Engine) -> None:
    profile_id = _profile(db_engine)
    with session_scope(db_engine) as session:
        source = get_or_create_aggregator_source(
            session, aggregator="remoteok", spec=SavedSearch(query="python"), profile_id=profile_id
        )
        persist_aggregated(
            session,
            source=source,
            discovered=[_aggregated("1", "https://x.test/1", company="")],
            clock=_fixed_clock,
        )
    with session_scope(db_engine) as session:
        postings = list_postings(session)
        company = session.get(Company, postings[0].company_id)
        assert company is not None
        assert company.name == "Unknown company"


def test_persist_aggregated_skips_duplicates(db_engine: Engine) -> None:
    profile_id = _profile(db_engine)
    with session_scope(db_engine) as session:
        source = get_or_create_aggregator_source(
            session, aggregator="remoteok", spec=SavedSearch(query="python"), profile_id=profile_id
        )
        persist_aggregated(
            session,
            source=source,
            discovered=[_aggregated("1", "https://x.test/1")],
            clock=_fixed_clock,
        )
    with session_scope(db_engine) as session:
        reloaded = get_aggregator_source(
            session, aggregator="remoteok", spec=SavedSearch(query="python"), profile_id=profile_id
        )
        assert reloaded is not None
        # Same external id → skipped; and a different id with the same normalized
        # apply URL is skipped by the cross-source dedupe hash.
        outcome = persist_aggregated(
            session,
            source=reloaded,
            discovered=[
                _aggregated("1", "https://x.test/1"),
                _aggregated("other", "https://x.test/1/"),
            ],
            clock=_fixed_clock,
        )
        assert outcome.discovered == 0
        assert outcome.skipped == 2
