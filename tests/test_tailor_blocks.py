"""Tests for the block mapping in :mod:`atlas.tailor.blocks`."""

from __future__ import annotations

from atlas.db.models import ResumeBlock
from atlas.tailor.blocks import render_blocks, tag_blocks_for_prompt
from atlas.tailor.structure import TailoredItem


def _block(content_id: str, block_type: str, text: str) -> ResumeBlock:
    return ResumeBlock(
        master_resume_id=1, type=block_type, content_id=content_id, position=0, text=text
    )


def test_tag_blocks_for_prompt() -> None:
    blocks = [
        _block("blk_a", "experience", "Led  the\nplatform team"),
        _block("blk_b", "skill", "Go"),
    ]
    tagged = tag_blocks_for_prompt(blocks)
    # Each block becomes a "[id] (type) text" line with whitespace collapsed.
    assert tagged.splitlines() == [
        "[blk_a] (experience) Led the platform team",
        "[blk_b] (skill) Go",
    ]


def test_render_blocks_maps_included_items_by_content_id() -> None:
    source = [_block("blk_a", "experience", "orig A"), _block("blk_b", "skill", "orig B")]
    items = [
        TailoredItem(content_id="blk_b", final_text="Python, Go", included=True),
        TailoredItem(content_id="blk_a", final_text="Led platform team", included=True),
    ]
    rendered = render_blocks(items, source)
    # Order follows items (the AI's chosen order), type comes from the source block.
    assert [(b.content_id, b.type, b.text, b.position) for b in rendered] == [
        ("blk_b", "skill", "Python, Go", 0),
        ("blk_a", "experience", "Led platform team", 1),
    ]


def test_render_blocks_drops_excluded_and_unknown_ids() -> None:
    source = [_block("blk_a", "experience", "orig A")]
    items = [
        TailoredItem(content_id="blk_a", final_text="kept", included=True),
        TailoredItem(content_id="blk_a", final_text="dropped", included=False),
        TailoredItem(content_id="blk_ZZZ", final_text="hallucinated", included=True),
    ]
    rendered = render_blocks(items, source)
    assert [b.text for b in rendered] == ["kept"]


def test_render_blocks_falls_back_to_source_text_when_blank() -> None:
    source = [_block("blk_a", "experience", "original text")]
    rendered = render_blocks([TailoredItem(content_id="blk_a", final_text="   ")], source)
    assert rendered[0].text == "original text"
