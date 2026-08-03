"""Tests for the ingest orchestration in :mod:`atlas.scrape.service`."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytest

from atlas.db import session_scope
from atlas.scrape.errors import ExtractionError
from atlas.scrape.fetcher import FetchResult
from atlas.scrape.repository import get_posting, list_postings
from atlas.scrape.service import add_posting, dedupe_hash_for, normalize_url
from tests.conftest import FakeFetcher, FakeLLMProvider, make_response

if TYPE_CHECKING:
    from pathlib import Path

    from sqlalchemy.engine import Engine

_CLOCK = datetime(2026, 8, 3, 9, 0, tzinfo=UTC)

_JSONLD_PAGE = """
<html><head>
<script type="application/ld+json">
{"@type": "JobPosting", "title": "Backend Engineer",
 "hiringOrganization": {"name": "Acme"}, "description": "Build things."}
</script></head><body>Backend Engineer at Acme. Build reliable things all day.</body></html>
"""


def _fixed_clock() -> datetime:
    return _CLOCK


def _fetch_result(body: str, url: str = "https://jobs.acme.test/backend") -> FetchResult:
    return FetchResult(url=url, status_code=200, content_type="text/html", body=body)


def _no_ai() -> FakeLLMProvider:
    # A provider that must not be called (structured extraction short-circuits it).
    return FakeLLMProvider([])


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("HTTPS://Jobs.ACME.test:443/backend/", "https://jobs.acme.test/backend"),
        ("http://x.test:8080/a?b=1#frag", "http://x.test:8080/a?b=1"),
        ("https://x.test/a/", "https://x.test/a"),
    ],
)
def test_normalize_url(raw: str, expected: str) -> None:
    assert normalize_url(raw) == expected


def test_dedupe_hash_is_stable_across_cosmetic_url_differences() -> None:
    assert dedupe_hash_for("https://x.test/a/") == dedupe_hash_for("HTTPS://x.test/a")


def test_add_posting_first_time_creates_everything(db_engine: Engine, tmp_path: Path) -> None:
    fetcher = FakeFetcher(_fetch_result(_JSONLD_PAGE))
    with session_scope(db_engine) as session:
        outcome = add_posting(
            session,
            "https://jobs.acme.test/backend",
            provider=_no_ai(),
            fetcher=fetcher,
            snapshots_dir=tmp_path,
            clock=_fixed_clock,
        )
    assert outcome.created is True
    assert outcome.title == "Backend Engineer"
    assert outcome.company == "Acme"
    # Structured extraction short-circuited the AI (provider never called).
    with session_scope(db_engine) as session:
        stored = get_posting(session, outcome.posting_id)
        assert stored.fetched_at == _CLOCK
        assert stored.raw_snapshot_ref is not None
    # Snapshot written to the injected dir.
    assert list(tmp_path.glob("*.html"))


def test_add_posting_same_url_is_noop(db_engine: Engine, tmp_path: Path) -> None:
    fetcher = FakeFetcher(_fetch_result(_JSONLD_PAGE))
    url = "https://jobs.acme.test/backend"
    with session_scope(db_engine) as session:
        first = add_posting(
            session,
            url,
            provider=_no_ai(),
            fetcher=fetcher,
            snapshots_dir=tmp_path,
            clock=_fixed_clock,
        )
    with session_scope(db_engine) as session:
        second = add_posting(
            session,
            url + "/",
            provider=_no_ai(),
            fetcher=fetcher,
            snapshots_dir=tmp_path,
            clock=_fixed_clock,
        )
    assert second.created is False
    assert second.posting_id == first.posting_id
    assert second.company == "Acme"
    with session_scope(db_engine) as session:
        assert len(list_postings(session)) == 1


def test_add_posting_uses_ai_when_no_structured_data(db_engine: Engine, tmp_path: Path) -> None:
    page = "<html><body><p>" + "words " * 60 + "</p></body></html>"
    fetcher = FakeFetcher(_fetch_result(page))
    provider = FakeLLMProvider(
        [make_response(structured={"title": "AI Role", "company": "Globex"})]
    )
    with session_scope(db_engine) as session:
        outcome = add_posting(
            session,
            "https://jobs.globex.test/role",
            provider=provider,
            fetcher=fetcher,
            snapshots_dir=tmp_path,
            clock=_fixed_clock,
        )
    assert outcome.created is True
    assert outcome.title == "AI Role"
    assert outcome.company == "Globex"


def test_add_posting_raises_when_nothing_extractable(db_engine: Engine, tmp_path: Path) -> None:
    # No structured data and the AI degrades to an empty-title posting → error.
    page = "<html><body><p>" + "filler " * 60 + "</p></body></html>"
    fetcher = FakeFetcher(_fetch_result(page))
    provider = FakeLLMProvider([make_response(text="no json") for _ in range(4)])
    with session_scope(db_engine) as session, pytest.raises(ExtractionError):
        add_posting(
            session,
            "https://jobs.example.test/x",
            provider=provider,
            fetcher=fetcher,
            snapshots_dir=tmp_path,
            clock=_fixed_clock,
        )


def test_add_posting_uses_browser_for_js_shell(db_engine: Engine, tmp_path: Path) -> None:
    # A near-empty static body triggers the browser fallback, which returns the real page.
    static = FakeFetcher(_fetch_result("<html><body></body></html>"))
    rendered = FakeFetcher(_fetch_result(_JSONLD_PAGE))
    with session_scope(db_engine) as session:
        outcome = add_posting(
            session,
            "https://jobs.acme.test/backend",
            provider=_no_ai(),
            fetcher=static,
            browser_fetch=rendered,
            snapshots_dir=tmp_path,
            clock=_fixed_clock,
        )
    assert outcome.created is True
    assert outcome.title == "Backend Engineer"
    assert rendered.calls  # the browser fallback was used
