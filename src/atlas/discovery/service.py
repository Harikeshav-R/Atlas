"""Watchlist + discovery persistence orchestration (PROJECT.md §5.4).

Two domain operations over an open :class:`~sqlmodel.Session`:

- :func:`add_watchlist_company` — the ``atlas company add`` core: get-or-create the
  :class:`~atlas.db.models.Company` (recording its ATS type + board token) and the
  ATS :class:`~atlas.db.models.JobSource` that the poll iterates. Idempotent, so
  re-adding the same board is a no-op.
- :func:`persist_discovered` — turn an adapter's discovered postings
  (:class:`~atlas.discovery.structure.DiscoveredPosting`) into persisted
  :class:`~atlas.db.models.JobPosting` rows, **deduplicated** first by the source's
  own external id and then by the normalized-apply-URL ``dedupe_hash`` (so the same
  role discovered here and pasted via ``atlas add`` collapses into one), reusing the
  scraper's :func:`~atlas.scrape.service.dedupe_hash_for` and
  :func:`~atlas.scrape.repository.create_job_posting`.

The clock is injected (``utcnow`` default) so persisted ``fetched_at`` timestamps
are deterministic in tests (AGENTS.md §6.2).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel

from atlas.discovery.repository import (
    get_aggregator_source,
    get_ats_source,
    get_or_create_aggregator_source,
    get_or_create_ats_source,
    get_posting_by_source_external,
)
from atlas.resume.service import utcnow
from atlas.scrape.repository import (
    create_job_posting,
    get_or_create_company,
    get_posting_by_dedupe,
)
from atlas.scrape.service import dedupe_hash_for

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable
    from datetime import datetime

    from sqlmodel import Session

    from atlas.db.models import JobSource
    from atlas.discovery.aggregators.structure import SavedSearch
    from atlas.discovery.structure import DiscoveredPosting

__all__ = [
    "AddCompanyOutcome",
    "AddSearchOutcome",
    "PersistOutcome",
    "add_saved_search",
    "add_watchlist_company",
    "persist_aggregated",
    "persist_discovered",
]

#: Placeholder company name for an aggregator posting that names no company.
_UNKNOWN_COMPANY = "Unknown company"


class AddCompanyOutcome(BaseModel):
    """The result of :func:`add_watchlist_company`.

    Attributes:
        company_id: The watchlisted company's id.
        source_id: The ATS source's id (the pollable unit).
        name: The company's display name.
        ats_type: The detected ATS provider.
        board_token: The detected board token.
        created: Whether a new ATS source was created (``False`` when the board was
            already on the watchlist).
    """

    company_id: int
    source_id: int
    name: str
    ats_type: str
    board_token: str
    created: bool


class PersistOutcome(BaseModel):
    """The result of :func:`persist_discovered` for one source.

    Attributes:
        discovered: How many new postings were inserted.
        skipped: How many discovered postings were duplicates and skipped.
    """

    discovered: int
    skipped: int


class AddSearchOutcome(BaseModel):
    """The result of :func:`add_saved_search`.

    Attributes:
        source_id: The aggregator source's id (the pollable unit).
        aggregator: The aggregator provider name.
        query: The saved search's query text.
        profile_id: The owning profile's id (saved searches are per-profile).
        created: Whether a new source was created (``False`` when the same search
            was already saved for this profile).
    """

    source_id: int
    aggregator: str
    query: str
    profile_id: int
    created: bool


def add_watchlist_company(
    session: Session,
    *,
    name: str,
    ats_type: str,
    board_token: str,
    domain: str | None = None,
) -> AddCompanyOutcome:
    """Add (or reuse) a watchlisted company and its ATS source.

    Get-or-creates the :class:`~atlas.db.models.Company` by name (recording its
    ``ats_type`` / ``ats_board_ref`` / ``domain``) and the ATS
    :class:`~atlas.db.models.JobSource` by ``(ats_type, board_token)``. Re-adding
    the same board is idempotent (``created=False``).
    """
    company = get_or_create_company(session, name=name)
    company.ats_type = ats_type
    company.ats_board_ref = board_token
    if domain is not None:
        company.domain = domain
    session.add(company)
    session.flush()
    assert company.id is not None  # flushed rows always have an id
    existing = get_ats_source(session, ats_type=ats_type, board_token=board_token)
    source = get_or_create_ats_source(
        session, ats_type=ats_type, board_token=board_token, company_id=company.id
    )
    assert source.id is not None
    return AddCompanyOutcome(
        company_id=company.id,
        source_id=source.id,
        name=company.name,
        ats_type=ats_type,
        board_token=board_token,
        created=existing is None,
    )


def persist_discovered(
    session: Session,
    *,
    source: JobSource,
    company_id: int,
    discovered: Iterable[DiscoveredPosting],
    clock: Callable[[], datetime] = utcnow,
) -> PersistOutcome:
    """Persist new postings from ``discovered``, deduplicating existing ones.

    For each posting, skips it when the source already has that ``external_id`` or
    when its normalized-apply-URL ``dedupe_hash`` already exists (a cross-source
    duplicate); otherwise inserts a new :class:`~atlas.db.models.JobPosting`.

    Args:
        session: The open session/transaction to write within.
        source: The ATS source the postings came from.
        company_id: The owning company's id (posting FK).
        discovered: The adapter's normalized postings.
        clock: The clock for each posting's ``fetched_at`` (injectable for tests).

    Returns:
        A :class:`PersistOutcome` with the inserted and skipped counts.
    """
    assert source.id is not None  # persisted sources always have an id
    inserted = 0
    skipped = 0
    for item in discovered:
        if (
            get_posting_by_source_external(
                session, source_id=source.id, external_id=item.external_id
            )
            is not None
        ):
            skipped += 1
            continue
        dedupe = dedupe_hash_for(item.posting.apply_url)
        if get_posting_by_dedupe(session, dedupe) is not None:
            skipped += 1
            continue
        posting = item.posting
        create_job_posting(
            session,
            source_id=source.id,
            company_id=company_id,
            title=posting.title,
            apply_url=posting.apply_url,
            dedupe_hash=dedupe,
            fetched_at=clock(),
            location=posting.location,
            remote_type=posting.remote_type,
            employment_type=posting.employment_type,
            seniority=posting.seniority,
            salary=posting.salary,
            description=posting.description,
            requirements=posting.requirements.model_dump(mode="json"),
            keywords=posting.keywords,
            external_id=item.external_id,
        )
        inserted += 1
    return PersistOutcome(discovered=inserted, skipped=skipped)


def add_saved_search(
    session: Session,
    *,
    aggregator: str,
    spec: SavedSearch,
    profile_id: int,
) -> AddSearchOutcome:
    """Add (or reuse) a per-profile aggregator saved search.

    Get-or-creates the aggregator :class:`~atlas.db.models.JobSource` by the
    ``(aggregator, normalized search, profile_id)`` triple, so re-adding the same
    search for the same profile is idempotent (``created=False``). The caller is
    responsible for validating ``aggregator`` against the registry.
    """
    existing = get_aggregator_source(
        session, aggregator=aggregator, spec=spec, profile_id=profile_id
    )
    source = get_or_create_aggregator_source(
        session, aggregator=aggregator, spec=spec, profile_id=profile_id
    )
    assert source.id is not None  # flushed rows always have an id
    return AddSearchOutcome(
        source_id=source.id,
        aggregator=aggregator,
        query=spec.query,
        profile_id=profile_id,
        created=existing is None,
    )


def persist_aggregated(
    session: Session,
    *,
    source: JobSource,
    discovered: Iterable[DiscoveredPosting],
    clock: Callable[[], datetime] = utcnow,
) -> PersistOutcome:
    """Persist new aggregator postings, deduplicating existing ones.

    Like :func:`persist_discovered`, but an aggregator spans many companies, so the
    company is **not** supplied by the source — it is get-or-created per posting from
    :attr:`~atlas.scrape.structure.ScrapedPosting.company` (falling back to a
    placeholder when the aggregator names none). The two-tier dedup is identical:
    skip when the source already has that ``external_id``, then skip when the
    normalized-apply-URL ``dedupe_hash`` already exists (a cross-source duplicate).

    Args:
        session: The open session/transaction to write within.
        source: The aggregator source the postings came from.
        discovered: The adapter's normalized postings.
        clock: The clock for each posting's ``fetched_at`` (injectable for tests).

    Returns:
        A :class:`PersistOutcome` with the inserted and skipped counts.
    """
    assert source.id is not None  # persisted sources always have an id
    inserted = 0
    skipped = 0
    for item in discovered:
        if (
            get_posting_by_source_external(
                session, source_id=source.id, external_id=item.external_id
            )
            is not None
        ):
            skipped += 1
            continue
        dedupe = dedupe_hash_for(item.posting.apply_url)
        if get_posting_by_dedupe(session, dedupe) is not None:
            skipped += 1
            continue
        posting = item.posting
        company = get_or_create_company(session, name=posting.company or _UNKNOWN_COMPANY)
        assert company.id is not None  # flushed rows always have an id
        create_job_posting(
            session,
            source_id=source.id,
            company_id=company.id,
            title=posting.title,
            apply_url=posting.apply_url,
            dedupe_hash=dedupe,
            fetched_at=clock(),
            location=posting.location,
            remote_type=posting.remote_type,
            employment_type=posting.employment_type,
            seniority=posting.seniority,
            salary=posting.salary,
            description=posting.description,
            requirements=posting.requirements.model_dump(mode="json"),
            keywords=posting.keywords,
            external_id=item.external_id,
        )
        inserted += 1
    return PersistOutcome(discovered=inserted, skipped=skipped)
