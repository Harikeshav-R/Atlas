"""Tests for the fit-scoring models in :mod:`atlas.matching.structure`."""

from __future__ import annotations

from atlas.matching.structure import (
    DeterministicSignals,
    FitAssessment,
    SalaryFit,
    SignalStatus,
    Verdict,
)


def test_fit_assessment_defaults() -> None:
    assessment = FitAssessment()
    assert assessment.score == 0
    assert assessment.verdict is Verdict.STRETCH
    assert assessment.rationale == ""
    assert assessment.matched_strengths == []
    assert assessment.gaps == []
    assert assessment.dealbreaker_hits == []
    assert assessment.salary_fit is SalaryFit.UNKNOWN


def test_fit_assessment_validates_enum_strings() -> None:
    # complete_json validates the model from a dict; enum fields accept their
    # string values (as the AI returns them).
    assessment = FitAssessment.model_validate(
        {
            "score": 88,
            "verdict": "strong",
            "rationale": "Great overlap.",
            "matched_strengths": ["Python"],
            "gaps": ["Kubernetes"],
            "dealbreaker_hits": [],
            "salary_fit": "above",
        }
    )
    assert assessment.score == 88
    assert assessment.verdict is Verdict.STRONG
    assert assessment.salary_fit is SalaryFit.ABOVE


def test_fit_assessment_ignores_unknown_keys() -> None:
    # extra="ignore" keeps forward compatibility with a richer future schema.
    assessment = FitAssessment.model_validate({"score": 50, "unexpected": "field"})
    assert assessment.score == 50


def test_deterministic_signals_defaults() -> None:
    signals = DeterministicSignals()
    assert signals.salary is SalaryFit.UNKNOWN
    assert signals.location is SignalStatus.UNKNOWN
    assert signals.work_auth is SignalStatus.UNKNOWN
    assert signals.dealbreakers == []
