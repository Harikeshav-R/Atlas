"""Turn a job-posting URL into a normalized, persisted posting (PROJECT.md §5.5).

Atlas turns a user-pasted (or later, discovered) URL into a normalized
:class:`~atlas.db.models.JobPosting`. This package owns the fetch boundary
(:mod:`atlas.scrape.fetcher`), the deterministic JSON-LD/OpenGraph/main-text
extraction ladder (:mod:`atlas.scrape.extract`) with an AI extraction fallback
(:mod:`atlas.scrape.ai_extract`), the parsed-posting model
(:mod:`atlas.scrape.structure`), persistence over an open session
(:mod:`atlas.scrape.repository`), on-disk raw snapshots (:mod:`atlas.scrape.snapshot`),
the ingest orchestration (:mod:`atlas.scrape.service`), and the package error
hierarchy (:mod:`atlas.scrape.errors`).

Fetching is synchronous behind an injectable :class:`~atlas.scrape.fetcher.Fetcher`
protocol; the Playwright headless-browser fallback for JS-rendered pages plugs
into the :class:`~atlas.scrape.fetcher.BrowserFetcher` seam in a later step.
"""

from __future__ import annotations

from atlas.scrape.ai_extract import parse_job_posting
from atlas.scrape.errors import (
    ExtractionError,
    FetchError,
    JobPostingNotFoundError,
    ScrapeError,
)
from atlas.scrape.extract import (
    extract_jsonld,
    extract_main_text,
    extract_opengraph,
    extract_posting,
)
from atlas.scrape.fetcher import BrowserFetcher, Fetcher, FetchResult, default_fetcher
from atlas.scrape.repository import (
    create_job_posting,
    get_or_create_company,
    get_or_create_url_source,
    get_posting,
    get_posting_by_dedupe,
    list_postings,
)
from atlas.scrape.service import AddOutcome, add_posting, dedupe_hash_for, normalize_url
from atlas.scrape.snapshot import default_snapshots_dir, write_snapshot
from atlas.scrape.structure import Requirements, ScrapedPosting

__all__ = [
    "AddOutcome",
    "BrowserFetcher",
    "ExtractionError",
    "FetchError",
    "FetchResult",
    "Fetcher",
    "JobPostingNotFoundError",
    "Requirements",
    "ScrapeError",
    "ScrapedPosting",
    "add_posting",
    "create_job_posting",
    "dedupe_hash_for",
    "default_fetcher",
    "default_snapshots_dir",
    "extract_jsonld",
    "extract_main_text",
    "extract_opengraph",
    "extract_posting",
    "get_or_create_company",
    "get_or_create_url_source",
    "get_posting",
    "get_posting_by_dedupe",
    "list_postings",
    "normalize_url",
    "parse_job_posting",
    "write_snapshot",
]
