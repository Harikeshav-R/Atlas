"""Tests for the AI select-and-reword pass in :mod:`atlas.tailor.ai_tailor`."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from atlas.ai.base import LLMOutputError
from atlas.db.models import JobPosting, ResumeBlock
from atlas.tailor.ai_tailor import select_and_reword
from atlas.tailor.structure import TailoredResume
from tests.conftest import FakeLLMProvider, make_response

_FETCHED = datetime(2026, 8, 3, tzinfo=UTC)


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


def _blocks() -> list[ResumeBlock]:
    return [
        ResumeBlock(
            master_resume_id=1,
            type="experience",
            content_id="blk_a",
            position=0,
            text="Staff Engineer, Acme Jan 2020 - Mar 2026",
        )
    ]


def test_select_and_reword_happy_path() -> None:
    provider = FakeLLMProvider(
        [
            make_response(
                structured={
                    "items": [
                        {
                            "content_id": "blk_a",
                            "block_type": "experience",
                            "final_text": "Led platform team",
                            "reason": "core",
                            "included": True,
                        }
                    ],
                    "gaps": ["Kubernetes"],
                    "summary_rationale": "focus on platform",
                }
            )
        ]
    )
    tailored = select_and_reword(
        provider,
        posting=_posting(),
        company="Acme",
        emphasis=["distributed systems"],
        honesty_level="light_inference",
        blocks=_blocks(),
    )
    assert isinstance(tailored, TailoredResume)
    assert tailored.items[0].content_id == "blk_a"
    assert tailored.gaps == ["Kubernetes"]
    # The rendered prompt carried the content-ID-tagged blocks + honesty level + emphasis.
    prompt = provider.calls[0].prompt
    assert "[blk_a] (experience)" in prompt
    assert "light_inference" in prompt
    assert "distributed systems" in prompt


def test_select_and_reword_propagates_output_error() -> None:
    # 3 structured attempts + the prompt-only fallback all yield non-JSON, so
    # complete_json raises LLMOutputError — and select_and_reword does NOT swallow it.
    provider = FakeLLMProvider([make_response(text="not json") for _ in range(4)])
    with pytest.raises(LLMOutputError):
        select_and_reword(
            provider,
            posting=_posting(),
            company="Acme",
            emphasis=[],
            honesty_level="strict",
            blocks=_blocks(),
        )
