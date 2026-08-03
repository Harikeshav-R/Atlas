"""Score a stored job posting for fit against a profile (PROJECT.md §5.6, §7).

Atlas scores every candidate posting for fit rather than pre-filtering it away: for
a stored :class:`~atlas.db.models.JobPosting`, the active profile's preferences, and
a compact master-resume summary, it asks the AI for a structured fit assessment
(score, verdict, rationale, matched strengths, gaps, dealbreaker hits, salary fit)
while computing deterministic signals (salary / location / work-auth / deal-breakers)
that inform and annotate the score without discarding anything.

This package owns the assessment/signal models (:mod:`atlas.matching.structure`),
the deterministic signal computation (:mod:`atlas.matching.signals`), the compact
resume summary (:mod:`atlas.matching.summary`), the AI scoring pass
(:mod:`atlas.matching.ai_score`), persistence over an open session
(:mod:`atlas.matching.repository`), the scoring orchestration
(:mod:`atlas.matching.service`), and the package error hierarchy
(:mod:`atlas.matching.errors`).
"""

from __future__ import annotations

from atlas.matching.ai_score import score_fit
from atlas.matching.errors import (
    MatchingError,
    NoActiveProfileError,
    NoMasterResumeError,
    ScoringError,
)
from atlas.matching.repository import create_match_score, get_latest_match_score
from atlas.matching.service import ScoreOutcome, score_posting
from atlas.matching.signals import compute_signals
from atlas.matching.structure import (
    DeterministicSignals,
    FitAssessment,
    SalaryFit,
    SignalStatus,
    Verdict,
)
from atlas.matching.summary import build_resume_summary

__all__ = [
    "DeterministicSignals",
    "FitAssessment",
    "MatchingError",
    "NoActiveProfileError",
    "NoMasterResumeError",
    "SalaryFit",
    "ScoreOutcome",
    "ScoringError",
    "SignalStatus",
    "Verdict",
    "build_resume_summary",
    "compute_signals",
    "create_match_score",
    "get_latest_match_score",
    "score_fit",
    "score_posting",
]
