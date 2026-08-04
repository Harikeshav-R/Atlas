"""Typed structures for the cover-letter generator (PROJECT.md §5.8, §7).

A :class:`CoverLetterDraft` is the shape
:func:`atlas.ai.complete_json.complete_json` validates the ``write_cover_letter``
model output against: a structured letter (greeting, hook, body paragraphs, close)
grounded in the candidate's real material. Like :mod:`atlas.tailor.structure`, it
is a plain Pydantic model with no I/O — every field defaulted (so a partial result
still validates) and the base ignores unknown keys so a richer future schema still
loads.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

__all__ = ["CoverLetterDraft"]


class _Base(BaseModel):
    """Base model that ignores unknown keys (forward-compatible cover-letter output)."""

    model_config = ConfigDict(extra="ignore")


class CoverLetterDraft(_Base):
    """The AI's structured cover-letter draft (PROJECT.md §5.8, §7).

    Attributes:
        greeting: The salutation (e.g. ``"Dear Hiring Manager,"``).
        hook: The opening paragraph — why the candidate is writing / the pitch.
        body_paragraphs: 2-3 body paragraphs mapping real strengths to the role.
        closing: The closing line (e.g. ``"Sincerely,"``).
        gaps: Desired posting keywords/skills the candidate cannot truthfully
            claim (surfaced so the letter never fabricates them).
    """

    greeting: str = ""
    hook: str = ""
    body_paragraphs: list[str] = Field(default_factory=list)
    closing: str = ""
    gaps: list[str] = Field(default_factory=list)
