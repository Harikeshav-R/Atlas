"""Typed structures for the fit-scoring engine (PROJECT.md §5.6, §7).

A :class:`FitAssessment` is the shape :func:`atlas.ai.complete_json.complete_json`
validates the ``score_fit`` model output against, and a
:class:`DeterministicSignals` is the shape Atlas computes locally from the posting
and the profile preferences to inform and annotate the score without discarding
anything (PROJECT.md §5.6). Both are plain Pydantic models with no I/O — like
:mod:`atlas.scrape.structure` and :mod:`atlas.profiles.preferences`: every field is
defaulted (so a partial assessment is still valid), and the base ignores unknown
keys so a richer future schema still loads.

The service (:mod:`atlas.matching.service`) maps a :class:`FitAssessment` plus the
computed :class:`DeterministicSignals` onto the persisted
:class:`atlas.db.models.MatchScore` columns.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "DeterministicSignals",
    "FitAssessment",
    "QueueStatus",
    "SalaryFit",
    "SignalStatus",
    "Verdict",
]


class _Base(BaseModel):
    """Base model that ignores unknown keys (forward-compatible assessments).

    Mirrors :class:`atlas.scrape.structure._Base`: as the fit-assessment schema
    grows, an object produced by an older/newer model still loads (its now-unknown
    keys are dropped rather than rejected) — important because the AI pass may
    return extra fields.
    """

    model_config = ConfigDict(extra="ignore")


class Verdict(StrEnum):
    """The AI's overall fit verdict for a posting (PROJECT.md §5.6)."""

    STRONG = "strong"
    GOOD = "good"
    STRETCH = "stretch"
    WEAK = "weak"


class QueueStatus(StrEnum):
    """A posting's status in the TUI Discover queue (PROJECT.md §8 screen #2).

    Distinct from :class:`atlas.tracking.status.ApplicationStatus` (which tracks a
    prepared *application*): this is the *posting-level* triage a user does on the
    ranked queue of scored postings, before any application exists.

    - ``new`` *(default)*: a scored posting awaiting triage; shown in the queue.
    - ``saved``: flagged to revisit; still shown in the queue.
    - ``dismissed``: hidden from the queue (the user passed on it).
    """

    NEW = "new"
    SAVED = "saved"
    DISMISSED = "dismissed"


class SalaryFit(StrEnum):
    """How a posting's stated compensation fits the profile (PROJECT.md §5.6)."""

    ABOVE = "above"
    WITHIN = "within"
    BELOW = "below"
    UNKNOWN = "unknown"


class SignalStatus(StrEnum):
    """The status of a deterministic (non-salary) signal.

    ``MATCH`` and ``MISMATCH`` are definite; ``UNKNOWN`` covers the common case
    where the posting or the profile lacks the data to decide (PROJECT.md §5.6:
    signals annotate, they never silently discard).
    """

    MATCH = "match"
    MISMATCH = "mismatch"
    UNKNOWN = "unknown"


class FitAssessment(_Base):
    """The AI's structured fit assessment of a posting (PROJECT.md §5.6, §7).

    Attributes:
        score: The fit score, 0-100.
        verdict: The overall verdict — strong / good / stretch / weak.
        rationale: A 2-4 sentence explanation of the score.
        matched_strengths: Strengths the posting matches.
        gaps: Missing keywords/skills/requirements.
        dealbreaker_hits: Deal-breakers the posting triggers.
        salary_fit: The salary verdict — above / within / below / unknown.
    """

    score: int = 0
    verdict: Verdict = Verdict.STRETCH
    rationale: str = ""
    matched_strengths: list[str] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)
    dealbreaker_hits: list[str] = Field(default_factory=list)
    salary_fit: SalaryFit = SalaryFit.UNKNOWN


class DeterministicSignals(_Base):
    """Locally-computed signals passed to the prompt and shown as badges.

    These are computed from the posting and the profile preferences (never the
    LLM), passed into the scoring prompt as context, and persisted so the badges
    render on re-view without recomputing against a since-changed profile
    (PROJECT.md §5.6).

    Attributes:
        salary: How the posting's pay compares to the profile's floor/target.
        location: Whether the posting's location/remote posture is acceptable.
        work_auth: Whether the posting's work-authorization needs are compatible.
        dealbreakers: The profile deal-breakers the posting text appears to hit.
    """

    salary: SalaryFit = SalaryFit.UNKNOWN
    location: SignalStatus = SignalStatus.UNKNOWN
    work_auth: SignalStatus = SignalStatus.UNKNOWN
    dealbreakers: list[str] = Field(default_factory=list)
