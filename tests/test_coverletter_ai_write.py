"""Tests for the AI write pass in :mod:`atlas.coverletter.ai_write`."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from atlas.ai.base import LLMOutputError
from atlas.coverletter.ai_write import write_cover_letter
from atlas.coverletter.structure import CoverLetterDraft
from atlas.db.models import JobPosting
from tests.conftest import FakeLLMProvider, make_response

_FETCHED = datetime(2026, 8, 4, tzinfo=UTC)


def _posting() -> JobPosting:
    return JobPosting(
        source_id=1,
        company_id=1,
        title="Backend Engineer",
        description="Build reliable services.",
        requirements={"must": ["Python"]},
        keywords=["python"],
        apply_url="https://jobs.acme.test/1",
        fetched_at=_FETCHED,
        dedupe_hash="hash",
    )


def test_write_cover_letter_happy_path() -> None:
    provider = FakeLLMProvider(
        [
            make_response(
                structured={
                    "greeting": "Dear Hiring Manager,",
                    "hook": "I am excited to apply.",
                    "body_paragraphs": ["I led a platform team."],
                    "closing": "Sincerely,",
                    "gaps": ["Kubernetes"],
                }
            )
        ]
    )
    draft = write_cover_letter(
        provider,
        posting=_posting(),
        company="Acme",
        material="- Led the platform team",
        tone="professional",
        honesty_level="light_inference",
    )
    assert isinstance(draft, CoverLetterDraft)
    assert draft.greeting == "Dear Hiring Manager,"
    assert draft.gaps == ["Kubernetes"]
    # The rendered prompt carried the tone, honesty level, and grounding material.
    prompt = provider.calls[0].prompt
    assert "professional" in prompt
    assert "light_inference" in prompt
    assert "Led the platform team" in prompt


def test_write_cover_letter_propagates_output_error() -> None:
    provider = FakeLLMProvider([make_response(text="not json") for _ in range(4)])
    with pytest.raises(LLMOutputError):
        write_cover_letter(
            provider,
            posting=_posting(),
            company="Acme",
            material="stuff",
            tone="professional",
            honesty_level="strict",
        )
