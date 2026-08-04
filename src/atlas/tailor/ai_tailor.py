"""AI select-and-reword pass for tailoring (PROJECT.md §5.7 steps 1+3, §7).

Given a posting, the profile's tailoring emphasis, the honesty level, and the
master-resume blocks (content-ID-tagged), this asks the AI for a truth-anchored
:class:`~atlas.tailor.structure.TailoredResume` — a selection of relevant blocks
with reworded text, each keyed to a real ``content_id`` (the ``select_and_reword``
task, §7). It mirrors :mod:`atlas.matching.ai_score`: render the versioned prompt,
build an :class:`~atlas.ai.base.LLMRequest`, and drive it through
:func:`~atlas.ai.complete_json.complete_json`.

Like fit scoring — and unlike the scrape parser — it does **not** swallow
:class:`~atlas.ai.base.LLMOutputError`; a bogus tailored resume would mislead the
user, so the error propagates for the service to translate into a
:class:`~atlas.tailor.errors.TailoringOutputError`.

The function takes an already-built :class:`~atlas.ai.base.LLMProvider`, so the
hermetic suite drives it with a fake provider and no live call (AGENTS.md §6.2).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from atlas.ai.base import LLMRequest
from atlas.ai.complete_json import complete_json
from atlas.ai.prompts import SELECT_AND_REWORD_PROMPT_VERSION, render_prompt
from atlas.tailor.blocks import tag_blocks_for_prompt
from atlas.tailor.structure import TailoredResume

if TYPE_CHECKING:
    from atlas.ai.base import LLMProvider
    from atlas.db.models import JobPosting, ResumeBlock

__all__ = ["select_and_reword"]


def select_and_reword(
    provider: LLMProvider,
    *,
    posting: JobPosting,
    company: str,
    emphasis: list[str],
    honesty_level: str,
    blocks: list[ResumeBlock],
) -> TailoredResume:
    """Select and reword master-resume blocks for ``posting`` via the AI.

    Renders the versioned ``select_and_reword`` prompt with the posting fields,
    the profile's tailoring emphasis, the honesty level, and the content-ID-tagged
    blocks, then asks ``provider`` for JSON matching :class:`TailoredResume` via
    :func:`complete_json`.

    Args:
        provider: The AI backend (or failover chain) to call.
        posting: The stored posting to tailor toward.
        company: The posting's company name (resolved from its ``company_id``).
        emphasis: The active profile's tailoring emphasis themes.
        honesty_level: The resolved honesty level (``strict`` / ``reword_only`` /
            ``light_inference``) governing how far rewording may go.
        blocks: The master-resume version's blocks (the source of truth).

    Returns:
        The validated :class:`TailoredResume`.

    Raises:
        LLMOutputError: If the backend never produces schema-valid output. The
            caller translates this into a
            :class:`~atlas.tailor.errors.TailoringOutputError`.
    """
    prompt = render_prompt(
        "select_and_reword",
        SELECT_AND_REWORD_PROMPT_VERSION,
        title=posting.title,
        company=company,
        location=posting.location or "",
        seniority=posting.seniority or "",
        keywords=posting.keywords,
        requirements=posting.requirements,
        description=posting.description,
        emphasis=emphasis,
        honesty_level=honesty_level,
        blocks=tag_blocks_for_prompt(blocks),
    )
    request = LLMRequest(system=prompt.system, prompt=prompt.user)
    return complete_json(provider, request, TailoredResume)
