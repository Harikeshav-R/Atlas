"""Tests for the AI fit-scoring pass in :mod:`atlas.matching.ai_score`."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from atlas.ai.base import LLMOutputError
from atlas.db.models import JobPosting
from atlas.matching.ai_score import score_fit
from atlas.matching.structure import DeterministicSignals, SalaryFit, SignalStatus, Verdict
from atlas.profiles.preferences import ProfilePreferences
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


def test_score_fit_happy_path() -> None:
    provider = FakeLLMProvider(
        [
            make_response(
                structured={
                    "score": 84,
                    "verdict": "strong",
                    "rationale": "Strong overlap on the core stack.",
                    "matched_strengths": ["Python"],
                    "gaps": ["Kubernetes"],
                    "dealbreaker_hits": [],
                    "salary_fit": "within",
                }
            )
        ]
    )
    signals = DeterministicSignals(salary=SalaryFit.WITHIN, location=SignalStatus.MATCH)
    assessment = score_fit(
        provider,
        posting=_posting(),
        company="Acme",
        preferences=ProfilePreferences(target_roles=["Backend Engineer"]),
        resume_summary="Summary:\n- Shipped a distributed queue",
        signals=signals,
    )
    assert assessment.score == 84
    assert assessment.verdict is Verdict.STRONG
    assert assessment.salary_fit is SalaryFit.WITHIN
    # The rendered prompt carried the posting, company, resume summary, and signals.
    prompt = provider.calls[0].prompt
    assert "Backend Engineer" in prompt
    assert "Acme" in prompt
    assert "Shipped a distributed queue" in prompt
    assert "within" in prompt


def test_score_fit_propagates_output_error() -> None:
    # 3 structured attempts + the prompt-only fallback all yield non-JSON, so
    # complete_json raises LLMOutputError — and score_fit does NOT swallow it
    # (a bogus score must not enter the queue).
    provider = FakeLLMProvider([make_response(text="not json") for _ in range(4)])
    with pytest.raises(LLMOutputError):
        score_fit(
            provider,
            posting=_posting(),
            company="Acme",
            preferences=ProfilePreferences(),
            resume_summary="Summary:\n- did stuff",
            signals=DeterministicSignals(),
        )
