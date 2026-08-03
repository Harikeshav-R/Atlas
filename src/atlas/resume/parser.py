"""Deterministic Markdown master-resume parser (PROJECT.md §5.3).

:func:`parse_markdown` splits a Markdown resume into ordered, content-ID'd
:class:`~atlas.resume.structure.ParsedBlock`s using heading conventions: the
leading title and the lines under it become contact blocks, ``##`` sections map
to a :class:`~atlas.resume.structure.BlockType` by keyword, and within a section
each bullet, ``###`` sub-heading, and paragraph becomes its own block. Input with
no heading structure is still captured best-effort (each paragraph becomes an
``other`` block) so nothing is silently dropped.

An AI-assisted structure extractor (the ``parse_master_resume`` task, PROJECT.md
§7) is **not** wired here yet; the :class:`StructureExtractor` seam is the branch
point where it will plug in — passed as ``fallback``, it is consulted only when
the deterministic pass finds no heading structure to anchor on. Today every
caller passes ``fallback=None`` and gets the deterministic result.
"""

from __future__ import annotations

import re
from typing import Protocol

from atlas.resume.structure import (
    BlockType,
    ParsedBlock,
    ParsedResume,
    content_id_for,
    normalize_text,
)

__all__ = ["StructureExtractor", "normalize_markdown", "parse_markdown"]

#: An ATX heading: 1-6 leading ``#`` then at least one space then the text.
_HEADING = re.compile(r"^(#{1,6})\s+(.*)$")

#: An unordered-list bullet marker (``-``, ``*``, or ``+``) then the item text.
_BULLET = re.compile(r"^[-*+]\s+(.*)$")

#: Ordered ``(keyword, type)`` map for classifying a ``##`` section from its
#: heading text (first substring match wins; unmatched → ``OTHER``).
_SECTION_KEYWORDS: tuple[tuple[str, BlockType], ...] = (
    ("experience", BlockType.EXPERIENCE),
    ("work", BlockType.EXPERIENCE),
    ("employment", BlockType.EXPERIENCE),
    ("project", BlockType.PROJECT),
    ("skill", BlockType.SKILL),
    ("education", BlockType.EDUCATION),
    ("summary", BlockType.SUMMARY),
    ("objective", BlockType.SUMMARY),
    ("about", BlockType.SUMMARY),
    ("profile", BlockType.SUMMARY),
    ("cert", BlockType.CERTIFICATION),
    ("publication", BlockType.PUBLICATION),
    ("contact", BlockType.CONTACT),
    ("link", BlockType.LINK),
)


class StructureExtractor(Protocol):
    """The seam for a future AI-assisted structure extraction (PROJECT.md §7).

    A structure extractor maps raw Markdown to a
    :class:`~atlas.resume.structure.ParsedResume`. The deterministic parser is
    the only implementation today; when the ``parse_master_resume`` AI task lands
    it will implement this protocol (wrapping
    :func:`atlas.ai.complete_json.complete_json`) and be passed to
    :func:`parse_markdown` as ``fallback`` — no change to the deterministic path.
    """

    def __call__(self, markdown: str) -> ParsedResume:
        """Extract structured blocks from ``markdown``."""


def normalize_markdown(text: str) -> str:
    """Return a canonical form of ``text`` for content-change detection.

    Normalizes line endings (via :meth:`str.splitlines`), strips trailing
    whitespace from each line, and drops leading and trailing blank lines, so two
    sources that differ only in those cosmetic ways compare equal. Internal blank
    lines are preserved because they separate paragraphs for the parser.
    """
    lines = [line.rstrip() for line in text.splitlines()]
    start = 0
    end = len(lines)
    while start < end and not lines[start]:
        start += 1
    while end > start and not lines[end - 1]:
        end -= 1
    return "\n".join(lines[start:end])


def parse_markdown(markdown: str, *, fallback: StructureExtractor | None = None) -> ParsedResume:
    """Parse ``markdown`` into a :class:`ParsedResume` of content-ID'd blocks.

    Runs the deterministic heading-based parser. When ``fallback`` is provided
    *and* the source has content but no heading structure to anchor on, the
    ambiguous source is handed to the fallback instead (the future AI extractor);
    with ``fallback=None`` (today's callers) the best-effort deterministic result
    is always returned.

    Args:
        markdown: The Markdown resume source.
        fallback: An optional structure extractor consulted only for
            heading-less, non-empty input; ``None`` disables the fallback.

    Returns:
        The parsed resume structure.
    """
    blocks, saw_heading = _parse_deterministic(markdown)
    if fallback is not None and blocks and not saw_heading:
        return fallback(markdown)
    return ParsedResume(blocks=blocks)


def _parse_deterministic(markdown: str) -> tuple[list[ParsedBlock], bool]:
    """Parse ``markdown`` deterministically into blocks.

    Returns the ordered blocks and whether any Markdown heading was seen (the
    signal :func:`parse_markdown` uses to decide whether to defer to a fallback).
    """
    blocks: list[ParsedBlock] = []
    occurrences: dict[tuple[BlockType, str], int] = {}
    section = BlockType.CONTACT  # content before the first ``##`` is the header
    saw_heading = False
    paragraph: list[str] = []

    def flush_paragraph() -> None:
        if paragraph:
            _add_block(blocks, occurrences, section, "\n".join(paragraph))
            paragraph.clear()

    for raw_line in markdown.splitlines():
        stripped = raw_line.strip()
        if not stripped:
            flush_paragraph()
            continue
        heading = _HEADING.match(stripped)
        if heading is not None:
            flush_paragraph()
            saw_heading = True
            level = len(heading.group(1))
            text = heading.group(2).strip()
            if level == 1:
                section = BlockType.CONTACT
                _add_block(blocks, occurrences, BlockType.CONTACT, text)
            elif level == 2:
                section = _section_type(text)  # section name itself is structural
            else:  # a ``###`` sub-heading is a content line within the section
                _add_block(blocks, occurrences, section, text)
            continue
        bullet = _BULLET.match(stripped)
        if bullet is not None:
            flush_paragraph()
            _add_block(blocks, occurrences, section, bullet.group(1).strip())
            continue
        paragraph.append(stripped)
    flush_paragraph()
    return blocks, saw_heading


def _add_block(
    blocks: list[ParsedBlock],
    occurrences: dict[tuple[BlockType, str], int],
    block_type: BlockType,
    text: str,
) -> None:
    """Append a block for ``text``, assigning a stable, duplicate-safe content id.

    Tracks how many identical (type, normalized-text) blocks have already been
    emitted so a genuine repeat gets a distinct-but-stable id via the occurrence
    index rather than colliding with its twin.
    """
    key = (block_type, normalize_text(text))
    occurrence = occurrences.get(key, 0)
    occurrences[key] = occurrence + 1
    blocks.append(
        ParsedBlock(
            type=block_type,
            content_id=content_id_for(block_type, text, occurrence=occurrence),
            position=len(blocks),
            text=text,
        )
    )


def _section_type(heading_text: str) -> BlockType:
    """Classify a ``##`` section heading into a :class:`BlockType` by keyword."""
    lowered = heading_text.lower()
    for keyword, block_type in _SECTION_KEYWORDS:
        if keyword in lowered:
            return block_type
    return BlockType.OTHER
