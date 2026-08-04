"""Assemble a cover-letter draft into a render view model (PROJECT.md §5.8, §5.11).

Pure, I/O-free mapping from the AI's
:class:`~atlas.coverletter.structure.CoverLetterDraft` into the
:class:`~atlas.render.structure.CoverLetterContext` a cover-letter theme renders
against — the hook and body paragraphs become the letter's ordered paragraphs.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from atlas.render.structure import CoverLetterContext

if TYPE_CHECKING:
    from atlas.coverletter.structure import CoverLetterDraft

__all__ = ["build_cover_letter_context"]


def build_cover_letter_context(
    draft: CoverLetterDraft,
    *,
    name: str,
    contact_lines: list[str],
    company: str,
    date: str,
) -> CoverLetterContext:
    """Assemble ``draft`` into a :class:`CoverLetterContext` for theme rendering.

    Args:
        draft: The AI's structured cover-letter draft.
        name: The candidate's display name (header + sign-off).
        contact_lines: The candidate's contact/header lines.
        company: The addressed company name.
        date: The letter's date line, as free text.

    Returns:
        A :class:`CoverLetterContext` with the hook and body paragraphs assembled
        into the letter's ordered paragraphs.
    """
    paragraphs = [para for para in (draft.hook, *draft.body_paragraphs) if para.strip()]
    return CoverLetterContext(
        name=name,
        contact_lines=list(contact_lines),
        date=date,
        company=company,
        greeting=draft.greeting,
        paragraphs=paragraphs,
        closing=draft.closing,
        signoff_name=name,
    )
