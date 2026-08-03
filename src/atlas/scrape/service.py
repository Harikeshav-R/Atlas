"""Ingest orchestration for a pasted job-posting URL (PROJECT.md §5.5).

:func:`add_posting` is the domain layer between the CLI and the repository. Over
an open :class:`~sqlmodel.Session`, with the network, browser, AI, snapshot
directory, and clock all injected, it:

1. normalizes the URL into a stable ``dedupe_hash`` and returns a **no-op** if a
   posting with that hash already exists (re-adding the same URL is idempotent);
2. fetches the page (static ``httpx``; the injected browser fallback when the
   static body looks JS-rendered and a fallback is available);
3. runs the deterministic extraction ladder, falling back to the AI pass when no
   structured data is found;
4. writes the raw HTML snapshot to disk and persists the normalized posting,
   getting-or-creating its company and the shared ``url`` source.

Every external boundary is injected, so the whole flow runs offline in tests with
a fake fetcher and a fake AI provider (AGENTS.md §6.2).
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from typing import TYPE_CHECKING
from urllib.parse import urlsplit, urlunsplit

from pydantic import BaseModel

from atlas.db.models import Company
from atlas.resume.service import utcnow
from atlas.scrape.ai_extract import parse_job_posting
from atlas.scrape.errors import ExtractionError
from atlas.scrape.extract import extract_posting
from atlas.scrape.fetcher import BrowserFetcher, Fetcher, FetchResult, default_fetcher
from atlas.scrape.repository import (
    create_job_posting,
    get_or_create_company,
    get_or_create_url_source,
    get_posting_by_dedupe,
)
from atlas.scrape.snapshot import write_snapshot

if TYPE_CHECKING:
    from datetime import datetime
    from pathlib import Path

    from sqlmodel import Session

    from atlas.ai.base import LLMProvider
    from atlas.scrape.structure import ScrapedPosting

__all__ = ["AddOutcome", "add_posting", "dedupe_hash_for", "normalize_url"]

#: Default per-fetch timeout in seconds.
_TIMEOUT_S = 30

#: Below this much visible text a static page is treated as JS-rendered and, when
#: a browser fetcher is available, retried through it.
_MIN_STATIC_TEXT = 200


class AddOutcome(BaseModel):
    """The result of :func:`add_posting`.

    Attributes:
        posting_id: The resulting posting's id.
        created: Whether a new posting was created (``False`` when the URL was
            already stored).
        title: The posting's title (for the CLI's confirmation message).
        company: The posting's company name.
    """

    posting_id: int
    created: bool
    title: str
    company: str


def normalize_url(url: str) -> str:
    """Return a canonical form of ``url`` for deduplication.

    Lowercases the scheme and host, drops a default port and any fragment, and
    strips a trailing slash from the path, so cosmetically different URLs for the
    same posting collapse to one.
    """
    parts = urlsplit(url.strip())
    scheme = parts.scheme.lower()
    netloc = parts.hostname or ""
    if parts.port is not None:
        default = {"http": 80, "https": 443}.get(scheme)
        if parts.port != default:
            netloc = f"{netloc}:{parts.port}"
    path = parts.path.rstrip("/")
    return urlunsplit((scheme, netloc, path, parts.query, ""))


def dedupe_hash_for(url: str) -> str:
    """Return the dedupe hash for ``url`` (sha256 of its normalized form)."""
    return hashlib.sha256(normalize_url(url).encode("utf-8")).hexdigest()


def _fetch(
    url: str,
    *,
    fetcher: Fetcher,
    browser_fetch: BrowserFetcher | None,
) -> FetchResult:
    """Fetch ``url`` statically, retrying via the browser when it looks JS-rendered."""
    result = fetcher(url, timeout_s=_TIMEOUT_S)
    if browser_fetch is not None and len(result.body.strip()) < _MIN_STATIC_TEXT:
        # The static page returned little markup (likely a JS shell); render it.
        return browser_fetch(url, timeout_s=_TIMEOUT_S)
    return result


def add_posting(
    session: Session,
    url: str,
    *,
    provider: LLMProvider,
    fetcher: Fetcher = default_fetcher,
    browser_fetch: BrowserFetcher | None = None,
    snapshots_dir: Path | None = None,
    clock: Callable[[], datetime] = utcnow,
) -> AddOutcome:
    """Scrape, parse, and persist the posting at ``url`` (idempotent by URL).

    Args:
        session: The open session/transaction to write within.
        url: The posting URL to add.
        provider: The AI backend for the extraction fallback.
        fetcher: The static fetch boundary (injectable for tests).
        browser_fetch: Optional JS-render fallback; ``None`` disables it.
        snapshots_dir: Where to write the raw HTML snapshot (injectable for tests).
        clock: The clock for ``fetched_at`` (injectable for tests).

    Returns:
        An :class:`AddOutcome` describing the resulting posting.

    Raises:
        FetchError: If the page cannot be fetched.
        ExtractionError: If neither structured data nor the AI pass yields a title.
    """
    dedupe = dedupe_hash_for(url)
    existing = get_posting_by_dedupe(session, dedupe)
    if existing is not None:
        assert existing.id is not None  # persisted rows always have an id
        return AddOutcome(
            posting_id=existing.id,
            created=False,
            title=existing.title,
            company=_company_name(session, existing.company_id),
        )

    result = _fetch(url, fetcher=fetcher, browser_fetch=browser_fetch)
    structured, main_text = extract_posting(result.body)
    if structured is not None:
        posting = structured
    else:
        posting = parse_job_posting(provider, page_text=main_text, url=url)
    posting = _with_apply_url(posting, url)
    if not posting.title:
        raise ExtractionError(f"Could not extract a job posting from {url}.")

    snapshot_ref = write_snapshot(result.body, dedupe_hash=dedupe, snapshots_dir=snapshots_dir)
    company = get_or_create_company(session, name=posting.company or "Unknown")
    source = get_or_create_url_source(session)
    assert company.id is not None
    assert source.id is not None
    created = create_job_posting(
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
        raw_snapshot_ref=snapshot_ref,
    )
    assert created.id is not None
    return AddOutcome(
        posting_id=created.id, created=True, title=created.title, company=company.name
    )


def _company_name(session: Session, company_id: int) -> str:
    """Return the name of the company with ``company_id`` (for the no-op message)."""
    company = session.get(Company, company_id)
    # The FK guarantees the row exists (a posting always has its company).
    assert company is not None
    return company.name


def _with_apply_url(posting: ScrapedPosting, url: str) -> ScrapedPosting:
    """Return ``posting`` with its apply URL set to ``url`` when it has none."""
    if posting.apply_url:
        return posting
    return posting.model_copy(update={"apply_url": url})
