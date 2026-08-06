"""Fit-scoring orchestration for a stored job posting (PROJECT.md §5.6).

:func:`score_posting` is the domain layer between the CLI and the repository. Over
an open :class:`~sqlmodel.Session`, with the AI provider and clock injected, it:

1. loads the posting (:mod:`atlas.scrape.repository`) and its company;
2. reads the caller-supplied profile's typed preferences (the caller resolves
   *which* profile — the active one for ``atlas score``, or every profile for the
   daemon's poll — so scoring is not tied to a single active profile);
3. loads the latest master-resume version and builds a compact summary
   (:mod:`atlas.matching.summary`), erroring if no resume is set;
4. computes the deterministic signals (:mod:`atlas.matching.signals`);
5. asks the AI for a :class:`~atlas.matching.structure.FitAssessment`
   (:mod:`atlas.matching.ai_score`), translating an
   :class:`~atlas.ai.base.LLMOutputError` into a
   :class:`~atlas.matching.errors.ScoringError`;
6. persists an append-only :class:`~atlas.db.models.MatchScore` row and returns a
   small serializable :class:`ScoreOutcome` for the CLI.

Every external boundary is injected, so the whole flow runs offline in tests with a
fake AI provider and a fixed clock (AGENTS.md §6.2).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel

from atlas.ai.base import LLMOutputError
from atlas.db.models import Company
from atlas.matching.ai_score import score_fit
from atlas.matching.errors import NoMasterResumeError, ScoringError
from atlas.matching.repository import create_match_score
from atlas.matching.signals import compute_signals
from atlas.matching.structure import DeterministicSignals
from atlas.matching.summary import build_resume_summary
from atlas.profiles.preferences import ProfilePreferences
from atlas.resume.repository import get_blocks, get_latest_master_resume
from atlas.resume.service import utcnow
from atlas.scrape.repository import get_posting

if TYPE_CHECKING:
    from collections.abc import Callable
    from datetime import datetime

    from sqlmodel import Session

    from atlas.ai.base import LLMProvider
    from atlas.db.models import Profile

__all__ = ["ScoreOutcome", "score_posting"]


class ScoreOutcome(BaseModel):
    """The result of :func:`score_posting`.

    Attributes:
        match_score_id: The persisted score row's id.
        posting_id: The scored posting's id.
        title: The posting's title (for the CLI's confirmation message).
        company: The posting's company name.
        score: The AI fit score, 0-100.
        verdict: The AI verdict.
        salary_fit: The AI salary verdict.
        rationale: The AI's explanation of the score.
        matched_strengths: Strengths the posting matches.
        gaps: Missing keywords/skills/requirements.
        dealbreaker_hits: Deal-breakers the posting triggers.
        signals: The computed deterministic signals.
    """

    match_score_id: int
    posting_id: int
    title: str
    company: str
    score: int
    verdict: str
    salary_fit: str
    rationale: str
    matched_strengths: list[str]
    gaps: list[str]
    dealbreaker_hits: list[str]
    signals: DeterministicSignals


def score_posting(
    session: Session,
    posting_id: int,
    *,
    profile: Profile,
    provider: LLMProvider,
    clock: Callable[[], datetime] = utcnow,
) -> ScoreOutcome:
    """Score the posting ``posting_id`` against ``profile`` and persist the assessment.

    The caller chooses the profile (the active one for ``atlas score``, or each
    profile in turn for the daemon's poll), so scoring is not tied to a single
    active profile.

    Args:
        session: The open session/transaction to work within.
        posting_id: The id of the posting to score.
        profile: The profile whose preferences the posting is scored against.
        provider: The AI backend (or failover chain) to call.
        clock: The clock for the score's ``created_at`` (injectable for tests).

    Returns:
        A :class:`ScoreOutcome` describing the persisted assessment.

    Raises:
        JobPostingNotFoundError: If no posting has ``posting_id``.
        NoMasterResumeError: If no master resume has been set.
        ScoringError: If the AI backend never produces a usable assessment.
    """
    posting = get_posting(session, posting_id)
    assert posting.id is not None  # persisted rows always have an id

    assert profile.id is not None  # persisted profiles always have an id
    preferences = ProfilePreferences.model_validate(profile.preferences)

    resume = get_latest_master_resume(session)
    if resume is None:
        raise NoMasterResumeError
    assert resume.id is not None
    resume_summary = build_resume_summary(get_blocks(session, resume.id))

    signals = compute_signals(posting, preferences)
    company_name = _company_name(session, posting.company_id)

    try:
        assessment = score_fit(
            provider,
            posting=posting,
            company=company_name,
            preferences=preferences,
            resume_summary=resume_summary,
            signals=signals,
        )
    except LLMOutputError as exc:
        raise ScoringError(f"Could not score posting {posting_id}: no usable assessment.") from exc

    created = create_match_score(
        session,
        job_posting_id=posting.id,
        profile_id=profile.id,
        score=assessment.score,
        verdict=assessment.verdict.value,
        rationale=assessment.rationale,
        matched_strengths=assessment.matched_strengths,
        gaps=assessment.gaps,
        dealbreaker_hits=assessment.dealbreaker_hits,
        salary_fit=assessment.salary_fit.value,
        signals=signals.model_dump(mode="json"),
        model=_provider_model(provider),
        created_at=clock(),
    )
    assert created.id is not None
    return ScoreOutcome(
        match_score_id=created.id,
        posting_id=posting.id,
        title=posting.title,
        company=company_name,
        score=assessment.score,
        verdict=assessment.verdict.value,
        salary_fit=assessment.salary_fit.value,
        rationale=assessment.rationale,
        matched_strengths=assessment.matched_strengths,
        gaps=assessment.gaps,
        dealbreaker_hits=assessment.dealbreaker_hits,
        signals=signals,
    )


def _company_name(session: Session, company_id: int) -> str:
    """Return the name of the company with ``company_id``.

    A posting always references an existing company (a non-null foreign key), so
    the lookup never misses.
    """
    company = session.get(Company, company_id)
    assert company is not None
    return company.name


def _provider_model(provider: LLMProvider) -> str:
    """Return the provider's name for the ``model`` audit column."""
    return provider.name
