"""Tests for the AI extraction pass in :mod:`atlas.scrape.ai_extract`."""

from __future__ import annotations

from atlas.scrape.ai_extract import parse_job_posting
from tests.conftest import FakeLLMProvider, make_response

_URL = "https://jobs.example.com/backend"


def test_parse_job_posting_happy_path() -> None:
    # The backend returns a structured object; complete_json validates it.
    provider = FakeLLMProvider(
        [
            make_response(
                structured={
                    "title": "Backend Engineer",
                    "company": "Acme",
                    "remote_type": "remote",
                    "requirements": {"must": ["Python"], "nice": ["Rust"]},
                    "keywords": ["python", "postgres"],
                }
            )
        ]
    )
    posting = parse_job_posting(provider, page_text="messy page text", url=_URL)
    assert posting.title == "Backend Engineer"
    assert posting.company == "Acme"
    assert posting.requirements.must == ["Python"]
    # The apply URL is always set from the passed url, never the model.
    assert posting.apply_url == _URL
    # The rendered prompt carried the page text (proves the template was used).
    assert "messy page text" in provider.calls[0].prompt


def test_parse_job_posting_degraded_mode_keeps_raw_text() -> None:
    # The backend never returns schema-valid JSON: 3 structured attempts + the
    # prompt-only fallback all yield non-JSON, so complete_json raises
    # LLMOutputError and the raw page text is kept as the description (§7).
    provider = FakeLLMProvider([make_response(text="sorry, no json") for _ in range(4)])
    posting = parse_job_posting(provider, page_text="raw job text", url=_URL)
    assert posting.title == ""
    assert posting.description == "raw job text"
    assert posting.apply_url == _URL
