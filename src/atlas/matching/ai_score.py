"""AI fit-scoring pass for a job posting (PROJECT.md §5.6, §7).

Given a stored posting, the active profile's preferences, a compact master-resume
summary, and the deterministic signals Atlas computed, this asks the AI backend for
a structured :class:`~atlas.matching.structure.FitAssessment` (the ``score_fit``
task, §7). It mirrors :mod:`atlas.scrape.ai_extract`: render the versioned prompt,
build an :class:`~atlas.ai.base.LLMRequest`, and drive it through
:func:`~atlas.ai.complete_json.complete_json`.

Unlike the scrape parser — which degrades to keeping the raw page text when the
model fails — a bogus fit score would pollute the ranked queue, so this does **not**
swallow :class:`~atlas.ai.base.LLMOutputError`. It propagates for the service to
translate into a :class:`~atlas.matching.errors.ScoringError`.

The function takes an already-built :class:`~atlas.ai.base.LLMProvider`, so the
hermetic suite drives it with a fake provider and no live call (AGENTS.md §6.2).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from atlas.ai.base import LLMRequest
from atlas.ai.complete_json import complete_json
from atlas.ai.prompts import SCORE_FIT_PROMPT_VERSION, render_prompt
from atlas.matching.structure import FitAssessment

if TYPE_CHECKING:
    from atlas.ai.base import LLMProvider
    from atlas.db.models import JobPosting
    from atlas.matching.structure import DeterministicSignals
    from atlas.profiles.preferences import ProfilePreferences

__all__ = ["score_fit"]


def score_fit(
    provider: LLMProvider,
    *,
    posting: JobPosting,
    company: str,
    preferences: ProfilePreferences,
    resume_summary: str,
    signals: DeterministicSignals,
) -> FitAssessment:
    """Assess ``posting`` against ``preferences`` + ``resume_summary`` via the AI.

    Renders the versioned ``score_fit`` prompt with the posting fields, the profile
    preferences, the compact resume summary, and the deterministic signals, then
    asks ``provider`` for JSON matching :class:`FitAssessment` via
    :func:`complete_json`.

    Args:
        provider: The AI backend (or failover chain) to call.
        posting: The stored posting to score.
        company: The posting's company name (resolved from its ``company_id``).
        preferences: The active profile's typed preferences.
        resume_summary: A compact plaintext summary of the master resume.
        signals: The deterministic signals computed for this posting.

    Returns:
        The validated :class:`FitAssessment`.

    Raises:
        LLMOutputError: If the backend never produces schema-valid output (after
            :func:`complete_json`'s full recovery ladder). The caller translates
            this into a :class:`~atlas.matching.errors.ScoringError`.
    """
    prompt = render_prompt(
        "score_fit",
        SCORE_FIT_PROMPT_VERSION,
        title=posting.title,
        company=company,
        location=posting.location or "",
        remote_type=posting.remote_type or "",
        employment_type=posting.employment_type or "",
        seniority=posting.seniority or "",
        salary=posting.salary,
        keywords=posting.keywords,
        requirements=posting.requirements,
        description=posting.description,
        preferences=preferences.model_dump(mode="json"),
        resume_summary=resume_summary,
        signals=signals.model_dump(mode="json"),
    )
    request = LLMRequest(system=prompt.system, prompt=prompt.user)
    return complete_json(provider, request, FitAssessment)
