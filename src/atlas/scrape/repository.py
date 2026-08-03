"""Persistence for scraped job postings (PROJECT.md §5.5, §6).

Like :mod:`atlas.resume.repository`, these are thin, pure functions over an
**open** :class:`~sqlmodel.Session`: the caller opens the transaction with
:func:`atlas.db.session.session_scope`, calls one or more of these, and the scope
commits (or rolls back) on exit. Nothing here opens its own session or engine.

The get-or-create helpers keep the paste-URL flow's supporting rows singular:
:func:`get_or_create_company` deduplicates companies by name, and
:func:`get_or_create_url_source` reuses one ``type="url"`` :class:`~atlas.db.models.JobSource`
row for every pasted posting — enforced in code, mirroring the single-user /
single-active-profile invariants in :mod:`atlas.profiles.repository`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlmodel import col, select

from atlas.db.models import Company, JobPosting, JobSource
from atlas.scrape.errors import JobPostingNotFoundError

if TYPE_CHECKING:
    from datetime import datetime

    from sqlmodel import Session

__all__ = [
    "URL_SOURCE_TYPE",
    "create_job_posting",
    "get_or_create_company",
    "get_or_create_url_source",
    "get_posting",
    "get_posting_by_dedupe",
    "list_postings",
]

#: The :class:`~atlas.db.models.JobSource` ``type`` for pasted URLs (PROJECT.md §5.4).
URL_SOURCE_TYPE = "url"


def get_or_create_company(session: Session, *, name: str) -> Company:
    """Return the company named ``name``, creating it if it does not exist.

    Deduplicates by exact name so re-adding a posting for the same company reuses
    its row rather than inserting a duplicate.
    """
    company = session.exec(select(Company).where(Company.name == name)).first()
    if company is None:
        company = Company(name=name)
        session.add(company)
        session.flush()
    return company


def get_or_create_url_source(session: Session) -> JobSource:
    """Return the shared ``type="url"`` job source, creating it once if needed."""
    source = session.exec(select(JobSource).where(JobSource.type == URL_SOURCE_TYPE)).first()
    if source is None:
        source = JobSource(type=URL_SOURCE_TYPE)
        session.add(source)
        session.flush()
    return source


def get_posting_by_dedupe(session: Session, dedupe_hash: str) -> JobPosting | None:
    """Return the posting with ``dedupe_hash``, or ``None`` if none exists."""
    return session.exec(select(JobPosting).where(JobPosting.dedupe_hash == dedupe_hash)).first()


def list_postings(session: Session) -> list[JobPosting]:
    """Return every stored posting ordered by id (insertion order)."""
    return list(session.exec(select(JobPosting).order_by(col(JobPosting.id))).all())


def get_posting(session: Session, posting_id: int) -> JobPosting:
    """Return the posting with ``posting_id``.

    Raises:
        JobPostingNotFoundError: If no posting has that id.
    """
    posting = session.get(JobPosting, posting_id)
    if posting is None:
        raise JobPostingNotFoundError(posting_id)
    return posting


def create_job_posting(
    session: Session,
    *,
    source_id: int,
    company_id: int,
    title: str,
    apply_url: str,
    dedupe_hash: str,
    fetched_at: datetime,
    location: str | None = None,
    remote_type: str | None = None,
    employment_type: str | None = None,
    seniority: str | None = None,
    salary: dict[str, Any] | None = None,
    description: str = "",
    requirements: dict[str, Any] | None = None,
    keywords: list[str] | None = None,
    posted_at: datetime | None = None,
    raw_snapshot_ref: str | None = None,
    external_id: str | None = None,
) -> JobPosting:
    """Insert a new :class:`~atlas.db.models.JobPosting` and return it (id assigned).

    Args:
        session: The open session/transaction to write within.
        source_id: The owning job source's id.
        company_id: The owning company's id.
        title: The role title.
        apply_url: The URL to apply at.
        dedupe_hash: The stable hash used to collapse duplicate postings.
        fetched_at: When the posting was fetched (timezone-aware UTC).
        location: The posting's location(s), if any.
        remote_type: On-site / hybrid / remote, if determinable.
        employment_type: Employment type, if determinable.
        seniority: The role's seniority, if determinable.
        salary: Salary details as a JSON object.
        description: The full description text.
        requirements: Requirements as a JSON object.
        keywords: Tech stack / keywords.
        posted_at: When the role was posted, if known (timezone-aware UTC).
        raw_snapshot_ref: On-disk path to the raw HTML snapshot, if any.
        external_id: The source's own id for the posting, if any.

    Returns:
        The created :class:`~atlas.db.models.JobPosting`.
    """
    posting = JobPosting(
        source_id=source_id,
        company_id=company_id,
        title=title,
        apply_url=apply_url,
        dedupe_hash=dedupe_hash,
        fetched_at=fetched_at,
        location=location,
        remote_type=remote_type,
        employment_type=employment_type,
        seniority=seniority,
        salary=salary or {},
        description=description,
        requirements=requirements or {},
        keywords=list(keywords or []),
        posted_at=posted_at,
        raw_snapshot_ref=raw_snapshot_ref,
        external_id=external_id,
    )
    session.add(posting)
    session.flush()
    return posting
