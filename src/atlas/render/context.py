"""Build a resume theme's view model from stored resume blocks (PROJECT.md §5.11).

Pure, I/O-free mapping from a master-resume version's content-ID'd
:class:`~atlas.db.models.ResumeBlock` rows into the :class:`ResumeContext` a theme
renders against. Contact blocks become the header/contact lines; the remaining
fit-relevant block types become titled sections in a fixed, readable order. Each
block's text is split into lines (a leading ``-``/``*``/``•`` marks a bullet, which
is normalized to a plain line) so a theme can lay entries out consistently.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from atlas.render.structure import ResumeContext, ResumeEntry, ResumeSection
from atlas.resume.structure import BlockType

if TYPE_CHECKING:
    from atlas.db.models import ResumeBlock

__all__ = ["build_resume_context"]

#: Body block types rendered as sections, in display order, each with its heading.
#: Contact blocks are handled separately (the header); types not listed (LINK,
#: OTHER) are folded in under a trailing "Additional" section so nothing is lost.
_SECTIONS: tuple[tuple[BlockType, str], ...] = (
    (BlockType.SUMMARY, "Summary"),
    (BlockType.EXPERIENCE, "Experience"),
    (BlockType.PROJECT, "Projects"),
    (BlockType.SKILL, "Skills"),
    (BlockType.EDUCATION, "Education"),
    (BlockType.CERTIFICATION, "Certifications"),
    (BlockType.PUBLICATION, "Publications"),
)

#: Block types folded into a trailing "Additional" section (kept, not dropped).
_ADDITIONAL_TYPES: tuple[BlockType, ...] = (BlockType.LINK, BlockType.OTHER)

#: Leading markers that denote a bullet line (normalized away for the theme).
_BULLET_PREFIXES: tuple[str, ...] = ("- ", "* ", "• ")


def build_resume_context(blocks: list[ResumeBlock], *, name: str) -> ResumeContext:
    """Group ``blocks`` into a :class:`ResumeContext` for theme rendering.

    Args:
        blocks: The master-resume version's blocks, already ordered by position.
        name: The candidate's display name (the resume header).

    Returns:
        A :class:`ResumeContext` with contact blocks as the header/contact lines
        and the remaining blocks grouped into ordered, titled sections.
    """
    by_type: dict[str, list[ResumeBlock]] = {}
    for block in blocks:
        by_type.setdefault(block.type, []).append(block)

    contact_lines: list[str] = []
    for block in by_type.get(BlockType.CONTACT.value, []):
        contact_lines.extend(_split_lines(block.text))

    sections: list[ResumeSection] = []
    for block_type, heading in _SECTIONS:
        entries = _entries_for(by_type.get(block_type.value, []))
        if entries:
            sections.append(ResumeSection(heading=heading, entries=entries))

    additional: list[ResumeBlock] = [
        block for block_type in _ADDITIONAL_TYPES for block in by_type.get(block_type.value, [])
    ]
    extra_entries = _entries_for(additional)
    if extra_entries:
        sections.append(ResumeSection(heading="Additional", entries=extra_entries))

    return ResumeContext(name=name, contact_lines=contact_lines, sections=sections)


def _entries_for(blocks: list[ResumeBlock]) -> list[ResumeEntry]:
    """Map blocks to non-empty :class:`ResumeEntry` objects (one per block)."""
    entries: list[ResumeEntry] = []
    for block in blocks:
        lines = _split_lines(block.text)
        if lines:
            entries.append(ResumeEntry(lines=lines))
    return entries


def _split_lines(text: str) -> list[str]:
    """Split ``text`` into trimmed, bullet-normalized, non-empty lines."""
    lines: list[str] = []
    for raw in text.splitlines():
        line = raw.strip()
        for prefix in _BULLET_PREFIXES:
            if line.startswith(prefix):
                line = line[len(prefix) :].strip()
                break
        if line:
            lines.append(line)
    return lines
