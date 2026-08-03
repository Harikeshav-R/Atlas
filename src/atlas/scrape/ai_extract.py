"""AI extraction pass for job postings (PROJECT.md §5.5, §7).

When the deterministic extractors (:mod:`atlas.scrape.extract`) find no structured
data, this is the fallback: send the page's visible text to the AI backend and ask
it to fill the normalized :class:`~atlas.scrape.structure.ScrapedPosting` fields
(the ``parse_job_posting`` task, §7). It is the **first place Atlas drives a model
from a command flow**.

The function takes an already-built :class:`~atlas.ai.base.LLMProvider`, so the
hermetic suite drives it with a fake provider and no live call (AGENTS.md §6.2).
Per §7's graceful-degradation rule, if the model never returns schema-valid JSON
(:class:`~atlas.ai.base.LLMOutputError` after ``complete_json``'s full recovery
ladder), the raw page text is kept as the description so the posting is still
saved for the user to fix, rather than losing it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from atlas.ai.base import LLMOutputError, LLMRequest
from atlas.ai.complete_json import complete_json
from atlas.ai.prompts import PARSE_JOB_POSTING_PROMPT_VERSION, render_prompt
from atlas.scrape.structure import ScrapedPosting

if TYPE_CHECKING:
    from atlas.ai.base import LLMProvider

__all__ = ["parse_job_posting"]


def parse_job_posting(provider: LLMProvider, *, page_text: str, url: str) -> ScrapedPosting:
    """Extract a :class:`ScrapedPosting` from ``page_text`` using the AI backend.

    Renders the versioned ``parse_job_posting`` prompt, asks ``provider`` for JSON
    matching :class:`ScrapedPosting` via :func:`complete_json`, and returns the
    validated posting with its ``apply_url`` set to ``url``.

    Degraded mode (§7): if the backend never produces schema-valid output,
    :class:`~atlas.ai.base.LLMOutputError` is caught and a minimal posting is
    returned instead — the raw ``page_text`` as the description and ``url`` as the
    apply URL — so a difficult page is still saved rather than lost.

    Args:
        provider: The AI backend (or failover chain) to call.
        page_text: The posting page's visible text.
        url: The posting's apply URL, recorded on the result.

    Returns:
        The extracted (or degraded) :class:`ScrapedPosting`.
    """
    prompt = render_prompt(
        "parse_job_posting",
        PARSE_JOB_POSTING_PROMPT_VERSION,
        page_text=page_text,
        url=url,
    )
    request = LLMRequest(system=prompt.system, prompt=prompt.user)
    try:
        posting = complete_json(provider, request, ScrapedPosting)
    except LLMOutputError:
        # The model never returned schema-valid JSON; keep the raw text so the
        # posting is still saved for the user to correct (PROJECT.md §7).
        return ScrapedPosting(description=page_text, apply_url=url)
    return posting.model_copy(update={"apply_url": url})
