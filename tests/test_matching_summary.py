"""Tests for the compact resume summary in :mod:`atlas.matching.summary`."""

from __future__ import annotations

from atlas.db.models import ResumeBlock
from atlas.matching.summary import build_resume_summary
from atlas.resume.structure import BlockType


def _block(block_type: BlockType, text: str, position: int = 0) -> ResumeBlock:
    return ResumeBlock(
        master_resume_id=1,
        type=block_type.value,
        content_id=f"blk_{position}",
        position=position,
        text=text,
    )


def test_build_summary_groups_relevant_sections_in_order() -> None:
    blocks = [
        _block(BlockType.EXPERIENCE, "Led the platform team", 0),
        _block(BlockType.SUMMARY, "Senior backend engineer", 1),
        _block(BlockType.SKILL, "Python, Postgres", 2),
        _block(BlockType.CONTACT, "sam@example.com", 3),  # omitted (not fit-relevant)
    ]
    summary = build_resume_summary(blocks)
    # Sections appear in the module's fixed order (Summary before Experience),
    # regardless of block position; contact is dropped.
    assert summary.index("Summary:") < summary.index("Skills:") < summary.index("Experience:")
    assert "Senior backend engineer" in summary
    assert "- Led the platform team" in summary
    assert "sam@example.com" not in summary


def test_build_summary_skips_blank_text() -> None:
    blocks = [_block(BlockType.SUMMARY, "   "), _block(BlockType.SKILL, "Go")]
    summary = build_resume_summary(blocks)
    assert "Summary:" not in summary  # the only summary block was blank
    assert "Skills:" in summary


def test_build_summary_empty_when_no_relevant_blocks() -> None:
    assert build_resume_summary([]) == ""
    assert build_resume_summary([_block(BlockType.LINK, "https://example.test")]) == ""


def test_build_summary_truncates_long_content() -> None:
    long_text = "x" * 10000
    summary = build_resume_summary([_block(BlockType.SUMMARY, long_text)])
    assert summary.endswith("…")
    assert len(summary) < len(long_text)
