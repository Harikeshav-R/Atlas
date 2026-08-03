"""Typed structures for the resume-tailoring engine (PROJECT.md §5.7, §7).

A :class:`TailoredResume` is the shape :func:`atlas.ai.complete_json.complete_json`
validates the ``select_and_reword`` model output against: a truth-anchored
selection of master-resume content, each item tracing back to a source block by
``content_id`` (the traceability anchor from :mod:`atlas.resume.structure`). Like
:mod:`atlas.matching.structure`, these are plain Pydantic models with no I/O —
every field defaulted (so a partial result still validates) and the base ignores
unknown keys so a richer future schema still loads.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

__all__ = ["TailoredItem", "TailoredResume"]


class _Base(BaseModel):
    """Base model that ignores unknown keys (forward-compatible tailoring output)."""

    model_config = ConfigDict(extra="ignore")


class TailoredItem(_Base):
    """One tailored block decision, keyed to a master-resume block.

    Attributes:
        content_id: The source :class:`~atlas.db.models.ResumeBlock`'s stable
            content id — the traceability anchor. An item whose id does not match
            a source block is dropped (anti-hallucination guard).
        block_type: The source block's type (for the AI's reference; the service
            uses the source block's own type when rendering).
        final_text: The tailored text for this block. Governed by the honesty
            level; must stay traceable to the source block's real content.
        reason: Why this block was selected/reworded (for the decisions log).
        included: Whether this block appears in the tailored resume. ``False``
            drops it (e.g. low relevance).
    """

    content_id: str = ""
    block_type: str = ""
    final_text: str = ""
    reason: str = ""
    included: bool = True


class TailoredResume(_Base):
    """The AI's tailored-resume selection (PROJECT.md §5.7 steps 1+3, §7).

    Attributes:
        items: The per-block tailoring decisions, in the intended display order.
        gaps: Desired posting keywords/skills that could not be truthfully
            supported from the master resume (feeds gap suggestions).
        summary_rationale: A short overall explanation of the tailoring approach.
    """

    items: list[TailoredItem] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)
    summary_rationale: str = ""
