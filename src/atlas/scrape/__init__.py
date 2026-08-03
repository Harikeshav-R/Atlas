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
from atlas.scrape.structure import Requirements, ScrapedPosting

__all__ = [
    "BrowserFetcher",
    "ExtractionError",
    "FetchError",
    "FetchResult",
    "Fetcher",
    "JobPostingNotFoundError",
    "Requirements",
    "ScrapeError",
    "ScrapedPosting",
    "default_fetcher",
    "extract_jsonld",
    "extract_main_text",
    "extract_opengraph",
    "extract_posting",
    "parse_job_posting",
]
