"""Tests for the resume view-model builder in :mod:`atlas.render.context`."""

from __future__ import annotations

from atlas.db.models import ResumeBlock
from atlas.render.context import build_resume_context
from atlas.resume.structure import BlockType


def _block(block_type: BlockType, text: str, position: int = 0) -> ResumeBlock:
    return ResumeBlock(
        master_resume_id=1,
        type=block_type.value,
        content_id=f"blk_{position}",
        position=position,
        text=text,
    )


def test_contact_becomes_header_and_sections_are_ordered() -> None:
    blocks = [
        _block(BlockType.EXPERIENCE, "Staff Engineer, Acme\n- Led the platform team", 0),
        _block(BlockType.CONTACT, "sam@example.com\n555-1234", 1),
        _block(BlockType.SUMMARY, "Senior backend engineer.", 2),
        _block(BlockType.SKILL, "Python, Postgres", 3),
    ]
    context = build_resume_context(blocks, name="Sam Lee")
    assert context.name == "Sam Lee"
    assert context.contact_lines == ["sam@example.com", "555-1234"]
    # Sections follow the module's fixed order (Summary before Experience),
    # regardless of block position; contact is not a section.
    assert [s.heading for s in context.sections] == ["Summary", "Experience", "Skills"]


def test_bullet_prefixes_are_normalized() -> None:
    blocks = [_block(BlockType.EXPERIENCE, "Staff Engineer\n- Led team\n* Cut latency\n• Shipped")]
    context = build_resume_context(blocks, name="Sam")
    entry = context.sections[0].entries[0]
    assert entry.lines == ["Staff Engineer", "Led team", "Cut latency", "Shipped"]


def test_unknown_types_fold_into_additional_section() -> None:
    blocks = [
        _block(BlockType.LINK, "github.com/sam"),
        _block(BlockType.OTHER, "Volunteer work"),
    ]
    context = build_resume_context(blocks, name="Sam")
    assert [s.heading for s in context.sections] == ["Additional"]
    assert len(context.sections[0].entries) == 2


def test_blank_blocks_and_empty_input_yield_no_sections() -> None:
    assert build_resume_context([], name="Sam").sections == []
    blocks = [_block(BlockType.SUMMARY, "   \n  ")]  # only whitespace
    context = build_resume_context(blocks, name="Sam")
    assert context.sections == []
