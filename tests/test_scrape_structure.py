"""Tests for the scraped-posting models in :mod:`atlas.scrape.structure`."""

from __future__ import annotations

from atlas.scrape.structure import Requirements, ScrapedPosting


def test_scraped_posting_defaults() -> None:
    posting = ScrapedPosting()
    assert posting.title == ""
    assert posting.company == ""
    assert posting.location is None
    assert posting.salary == {}
    assert posting.responsibilities == []
    assert posting.keywords == []
    assert posting.requirements == Requirements()
    assert posting.requirements.must == []
    assert posting.apply_url == ""


def test_scraped_posting_round_trip() -> None:
    posting = ScrapedPosting(
        title="Backend Engineer",
        company="Acme",
        remote_type="remote",
        salary={"min": 150000, "currency": "USD"},
        requirements=Requirements(must=["Python"], nice=["Rust"]),
        keywords=["python"],
        apply_url="https://jobs.acme.test/1",
    )
    restored = ScrapedPosting.model_validate(posting.model_dump(mode="json"))
    assert restored == posting
    assert restored.requirements.must == ["Python"]


def test_scraped_posting_ignores_unknown_keys() -> None:
    # Forward compatibility: an AI response with extra fields still loads.
    restored = ScrapedPosting.model_validate({"title": "X", "future_field": 1})
    assert restored.title == "X"
