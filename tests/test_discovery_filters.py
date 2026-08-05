"""Tests for :func:`atlas.discovery.aggregators.filters.matches_search`.

The shared, deterministic filter every aggregator applies after normalization.
Covers query-term matching across the searchable fields, the optional location
filter, and the tri-state ``remote`` filter (its ``True`` / ``False`` branches are
not both reachable through the two shipped adapters, so they are exercised here).
"""

from __future__ import annotations

import pytest

from atlas.discovery.aggregators.filters import matches_search
from atlas.discovery.aggregators.structure import SavedSearch
from atlas.scrape.structure import ScrapedPosting


def _posting(**kwargs: object) -> ScrapedPosting:
    base: dict[str, object] = {
        "title": "Backend Engineer",
        "company": "Acme",
        "keywords": ["python", "django"],
        "description": "Build services.",
        "location": "Remote - US",
        "remote_type": "remote",
    }
    base.update(kwargs)
    return ScrapedPosting(**base)  # type: ignore[arg-type]


def test_empty_query_matches() -> None:
    assert matches_search(_posting(), SavedSearch(query="")) is True


@pytest.mark.parametrize(
    "query",
    ["backend", "python", "Acme", "build", "BACKEND python"],
)
def test_query_terms_match_across_fields(query: str) -> None:
    assert matches_search(_posting(), SavedSearch(query=query)) is True


def test_query_requires_all_terms() -> None:
    assert matches_search(_posting(), SavedSearch(query="backend rust")) is False


def test_location_filter_matches_and_rejects() -> None:
    assert matches_search(_posting(), SavedSearch(query="", location="us")) is True
    assert matches_search(_posting(), SavedSearch(query="", location="berlin")) is False


def test_location_filter_against_missing_location() -> None:
    assert matches_search(_posting(location=None), SavedSearch(query="", location="us")) is False


@pytest.mark.parametrize(
    ("remote_type", "want", "expected"),
    [
        ("remote", True, True),
        ("remote", False, False),
        ("onsite", True, False),
        ("onsite", False, True),
    ],
)
def test_remote_filter(remote_type: str, want: bool, expected: bool) -> None:
    posting = _posting(remote_type=remote_type)
    assert matches_search(posting, SavedSearch(query="", remote=want)) is expected
