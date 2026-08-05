"""Persistence for the ATS watchlist and discovered postings (PROJECT.md §5.4, §6).

Like :mod:`atlas.scrape.repository`, these are thin, pure functions over an
**open** :class:`~sqlmodel.Session`: the caller opens the transaction with
:func:`atlas.db.session.session_scope`, calls one or more of these, and the scope
commits (or rolls back) on exit. Nothing here opens its own session or engine.

An ATS board is persisted as a :class:`~atlas.db.models.JobSource` row with
``type="ats"`` — the *pollable unit* the discovery poll iterates (``enabled`` /
``last_polled_at``). Its :attr:`~atlas.db.models.JobSource.config` JSON carries
``ats_type``, ``board_token``, and the owning ``company_id``, so a poll reads
everything it needs from one row without a join. The source is deduplicated by
``(ats_type, board_token)`` in code, mirroring the single ``type="url"`` source in
:func:`atlas.scrape.repository.get_or_create_url_source`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlmodel import col, select

from atlas.db.models import JobPosting, JobSource

if TYPE_CHECKING:
    from collections.abc import Sequence
    from datetime import datetime

    from sqlmodel import Session

    from atlas.discovery.aggregators.structure import SavedSearch

__all__ = [
    "AGGREGATOR_SOURCE_TYPE",
    "ATS_SOURCE_TYPE",
    "get_aggregator_source",
    "get_ats_source",
    "get_or_create_aggregator_source",
    "get_or_create_ats_source",
    "get_posting_by_source_external",
    "list_enabled_aggregator_sources",
    "list_enabled_ats_sources",
    "stamp_last_polled_at",
]

#: The :class:`~atlas.db.models.JobSource` ``type`` for ATS boards (PROJECT.md §5.4).
ATS_SOURCE_TYPE = "ats"

#: The :class:`~atlas.db.models.JobSource` ``type`` for aggregator saved searches
#: (PROJECT.md §5.4-B).
AGGREGATOR_SOURCE_TYPE = "aggregator"


def get_ats_source(session: Session, *, ats_type: str, board_token: str) -> JobSource | None:
    """Return the ATS source for ``(ats_type, board_token)``, or ``None``.

    The dedup key is the provider + board token pair, held in the source config
    (there is no dedicated column), so this scans the ``type="ats"`` rows in code.
    """
    for source in session.exec(select(JobSource).where(JobSource.type == ATS_SOURCE_TYPE)).all():
        if (
            source.config.get("ats_type") == ats_type
            and source.config.get("board_token") == board_token
        ):
            return source
    return None


def get_or_create_ats_source(
    session: Session, *, ats_type: str, board_token: str, company_id: int
) -> JobSource:
    """Return the ATS source for ``(ats_type, board_token)``, creating it if absent.

    Deduplicated by the provider + board token pair (in code), so watchlisting the
    same board twice reuses its row rather than inserting a duplicate. The owning
    ``company_id`` is stored in the source config so the poll can attribute
    discovered postings without a join.
    """
    existing = get_ats_source(session, ats_type=ats_type, board_token=board_token)
    if existing is not None:
        return existing
    source = JobSource(
        type=ATS_SOURCE_TYPE,
        config={"ats_type": ats_type, "board_token": board_token, "company_id": company_id},
    )
    session.add(source)
    session.flush()
    return source


def list_enabled_ats_sources(session: Session) -> Sequence[JobSource]:
    """Return every enabled ``type="ats"`` source, ordered by id (poll order).

    The discovery poll iterates these; disabled sources and non-ATS sources (the
    shared ``type="url"`` source, future aggregators) are excluded.
    """
    return session.exec(
        select(JobSource)
        .where(JobSource.type == ATS_SOURCE_TYPE)
        .where(col(JobSource.enabled).is_(True))
        .order_by(col(JobSource.id))
    ).all()


def stamp_last_polled_at(session: Session, source: JobSource, when: datetime) -> None:
    """Record that ``source`` was polled at ``when`` (timezone-aware UTC)."""
    source.last_polled_at = when
    session.add(source)
    session.flush()


def get_posting_by_source_external(
    session: Session, *, source_id: int, external_id: str
) -> JobPosting | None:
    """Return the posting with ``external_id`` from ``source_id``, or ``None``.

    The stable per-source re-poll key: a board's job keeps the same external id
    across polls, so this is what the discovery service checks first before
    inserting (the normalized-URL ``dedupe_hash`` is the cross-source fallback).
    """
    return session.exec(
        select(JobPosting)
        .where(JobPosting.source_id == source_id)
        .where(JobPosting.external_id == external_id)
    ).first()


def get_aggregator_source(
    session: Session, *, aggregator: str, spec: SavedSearch, profile_id: int
) -> JobSource | None:
    """Return the aggregator source for this saved search, or ``None``.

    The dedup key is the ``(aggregator, normalized search, profile_id)`` triple,
    held in the source config (there is no dedicated column), so this scans the
    ``type="aggregator"`` rows in code. The search is normalized via
    :meth:`~pydantic.BaseModel.model_dump` so two specs that differ only in field
    order or defaulting compare equal.
    """
    wanted = spec.model_dump(mode="json")
    for source in session.exec(
        select(JobSource).where(JobSource.type == AGGREGATOR_SOURCE_TYPE)
    ).all():
        if (
            source.config.get("aggregator") == aggregator
            and source.config.get("search") == wanted
            and source.profile_id == profile_id
        ):
            return source
    return None


def get_or_create_aggregator_source(
    session: Session, *, aggregator: str, spec: SavedSearch, profile_id: int
) -> JobSource:
    """Return the aggregator source for this saved search, creating it if absent.

    Deduplicated by the ``(aggregator, normalized search, profile_id)`` triple (in
    code), so re-adding the same saved search reuses its row rather than inserting a
    duplicate. The search spec is stored in the source config so the poll can
    rebuild it without a join.
    """
    existing = get_aggregator_source(
        session, aggregator=aggregator, spec=spec, profile_id=profile_id
    )
    if existing is not None:
        return existing
    source = JobSource(
        type=AGGREGATOR_SOURCE_TYPE,
        config={"aggregator": aggregator, "search": spec.model_dump(mode="json")},
        profile_id=profile_id,
    )
    session.add(source)
    session.flush()
    return source


def list_enabled_aggregator_sources(session: Session) -> Sequence[JobSource]:
    """Return every enabled ``type="aggregator"`` source, ordered by id (poll order).

    The aggregator poll iterates these; disabled sources and non-aggregator sources
    (ATS boards, the shared ``type="url"`` source) are excluded.
    """
    return session.exec(
        select(JobSource)
        .where(JobSource.type == AGGREGATOR_SOURCE_TYPE)
        .where(col(JobSource.enabled).is_(True))
        .order_by(col(JobSource.id))
    ).all()
