"""Tests for the scrape error hierarchy in :mod:`atlas.scrape.errors`."""

from __future__ import annotations

from atlas.scrape.errors import (
    ExtractionError,
    FetchError,
    JobPostingNotFoundError,
    ScrapeError,
)


def test_job_posting_not_found_carries_id_and_message() -> None:
    exc = JobPostingNotFoundError(7)
    assert exc.posting_id == 7
    assert "7" in str(exc)
    assert isinstance(exc, ScrapeError)


def test_error_hierarchy() -> None:
    assert issubclass(FetchError, ScrapeError)
    assert issubclass(ExtractionError, ScrapeError)
    assert issubclass(JobPostingNotFoundError, ScrapeError)
