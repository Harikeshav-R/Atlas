"""A compact master-resume summary for the scoring prompt (PROJECT.md §5.6, §7).

The ``score_fit`` task takes "a compact summary of the master resume" (PROJECT.md
§5.6) rather than the full document, to keep the prompt small and focused. This
module builds that summary deterministically from a version's
:class:`~atlas.db.models.ResumeBlock` rows: it foregrounds the summary, skills,
experience, project, and education blocks (the fit-relevant ones), groups them
under readable headings, and caps the total size so a very long resume still yields
a bounded prompt.

Pure and I/O-free — the caller (:mod:`atlas.matching.service`) reads the blocks
from the repository and passes them in.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from atlas.resume.structure import BlockType

if TYPE_CHECKING:
    from collections.abc import Iterable

    from atlas.db.models import ResumeBlock

__all__ = ["build_resume_summary"]

#: Block types included in the summary, in the order they appear, each with the
#: heading it renders under. Types not listed (contact, links, …) are omitted as
#: irrelevant to fit scoring.
_SECTIONS: tuple[tuple[BlockType, str], ...] = (
    (BlockType.SUMMARY, "Summary"),
    (BlockType.SKILL, "Skills"),
    (BlockType.EXPERIENCE, "Experience"),
    (BlockType.PROJECT, "Projects"),
    (BlockType.EDUCATION, "Education"),
    (BlockType.CERTIFICATION, "Certifications"),
)

#: Upper bound on the summary length (characters), so a very long resume still
#: yields a compact prompt. Chosen generously; truncation appends an ellipsis.
_MAX_CHARS = 6000


def build_resume_summary(blocks: Iterable[ResumeBlock]) -> str:
    """Build a compact, grouped plaintext summary of a resume's ``blocks``.

    Args:
        blocks: The master-resume version's blocks (any order; grouped by type
            here, preserving each type's relative order).

    Returns:
        A plaintext summary with ``Heading:`` sections and ``- bullet`` lines,
        capped at a bounded length. Empty when ``blocks`` has no summary-relevant
        content.
    """
    by_type: dict[str, list[str]] = {}
    for block in blocks:
        text = block.text.strip()
        if text:
            by_type.setdefault(block.type, []).append(text)

    lines: list[str] = []
    for block_type, heading in _SECTIONS:
        texts = by_type.get(block_type.value)
        if not texts:
            continue
        lines.append(f"{heading}:")
        lines.extend(f"- {text}" for text in texts)
        lines.append("")

    summary = "\n".join(lines).strip()
    if len(summary) > _MAX_CHARS:
        summary = summary[:_MAX_CHARS].rstrip() + "\n…"
    return summary
