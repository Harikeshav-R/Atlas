"""AI write pass for cover letters (PROJECT.md §5.8, §7).

Given a posting, the company, the candidate's grounding material (the tailored
resume's selections, or a compact master-resume summary), the desired tone, and
the honesty level, this asks the AI for a truth-anchored
:class:`~atlas.coverletter.structure.CoverLetterDraft` (the ``write_cover_letter``
task, §7). It mirrors :mod:`atlas.tailor.ai_tailor`: render the versioned prompt,
build an :class:`~atlas.ai.base.LLMRequest`, and drive it through
:func:`~atlas.ai.complete_json.complete_json`.

Like tailoring — and unlike the scrape parser — it does **not** swallow
:class:`~atlas.ai.base.LLMOutputError`; a bogus letter would mislead the user, so
the error propagates for the service to translate into a
:class:`~atlas.coverletter.errors.CoverLetterOutputError`.

The function takes an already-built :class:`~atlas.ai.base.LLMProvider`, so the
hermetic suite drives it with a fake provider and no live call (AGENTS.md §6.2).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from atlas.ai.base import LLMRequest
from atlas.ai.complete_json import complete_json
from atlas.ai.prompts import WRITE_COVER_LETTER_PROMPT_VERSION, render_prompt
from atlas.coverletter.structure import CoverLetterDraft

if TYPE_CHECKING:
    from atlas.ai.base import LLMProvider
    from atlas.db.models import JobPosting

__all__ = ["write_cover_letter"]


def write_cover_letter(
    provider: LLMProvider,
    *,
    posting: JobPosting,
    company: str,
    material: str,
    tone: str,
    honesty_level: str,
) -> CoverLetterDraft:
    """Draft a :class:`CoverLetterDraft` for ``posting`` via the AI.

    Renders the versioned ``write_cover_letter`` prompt with the posting fields,
    the company, the candidate's grounding ``material``, the tone, and the honesty
    level, then asks ``provider`` for JSON matching :class:`CoverLetterDraft` via
    :func:`complete_json`.

    Args:
        provider: The AI backend (or failover chain) to call.
        posting: The stored posting the letter is for.
        company: The posting's company name.
        material: The candidate's grounding text — the tailored resume's
            selections or a compact master-resume summary.
        tone: The desired tone (e.g. ``"professional"``).
        honesty_level: The resolved honesty level governing how far claims may go.

    Returns:
        The validated :class:`CoverLetterDraft`.

    Raises:
        LLMOutputError: If the backend never produces schema-valid output. The
            caller translates this into a
            :class:`~atlas.coverletter.errors.CoverLetterOutputError`.
    """
    prompt = render_prompt(
        "write_cover_letter",
        WRITE_COVER_LETTER_PROMPT_VERSION,
        title=posting.title,
        company=company,
        location=posting.location or "",
        keywords=posting.keywords,
        requirements=posting.requirements,
        description=posting.description,
        tone=tone,
        honesty_level=honesty_level,
        material=material,
    )
    request = LLMRequest(system=prompt.system, prompt=prompt.user)
    return complete_json(provider, request, CoverLetterDraft)
