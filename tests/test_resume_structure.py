"""Tests for the parsed-structure models in :mod:`atlas.resume.structure`."""

from __future__ import annotations

import pytest

from atlas.resume.structure import (
    BlockType,
    ParsedBlock,
    ParsedResume,
    content_id_for,
    normalize_text,
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("  hello  world ", "hello world"),
        ("hello\n\tworld", "hello world"),
        ("no-extra-space", "no-extra-space"),
        ("   ", ""),
    ],
)
def test_normalize_text(raw: str, expected: str) -> None:
    assert normalize_text(raw) == expected


def test_content_id_is_stable_and_prefixed() -> None:
    first = content_id_for(BlockType.EXPERIENCE, "Shipped a thing")
    second = content_id_for(BlockType.EXPERIENCE, "Shipped a thing")
    assert first == second
    assert first.startswith("blk_")
    assert len(first) == len("blk_") + 12


def test_content_id_ignores_cosmetic_whitespace() -> None:
    assert content_id_for(BlockType.SKILL, "Python, Rust") == content_id_for(
        BlockType.SKILL, "  Python,   Rust  "
    )


def test_content_id_differs_by_type_and_text_and_occurrence() -> None:
    text = "Built the pipeline"
    by_text = content_id_for(BlockType.EXPERIENCE, text)
    assert by_text != content_id_for(BlockType.EXPERIENCE, "Built the platform")
    assert by_text != content_id_for(BlockType.PROJECT, text)
    # A repeated identical block disambiguates via the occurrence index.
    assert by_text != content_id_for(BlockType.EXPERIENCE, text, occurrence=1)


def test_parsed_block_defaults() -> None:
    block = ParsedBlock(
        type=BlockType.SUMMARY, content_id="blk_abc123456789", position=0, text="Engineer"
    )
    assert block.tags == {}


def test_parsed_resume_defaults_and_round_trip() -> None:
    assert ParsedResume().blocks == []
    resume = ParsedResume(
        blocks=[
            ParsedBlock(
                type=BlockType.SKILL,
                content_id="blk_000000000000",
                position=0,
                text="Python",
                tags={"level": "expert"},
            )
        ]
    )
    restored = ParsedResume.model_validate(resume.model_dump(mode="json"))
    assert restored == resume
    assert restored.blocks[0].type is BlockType.SKILL


def test_parsed_resume_ignores_unknown_keys() -> None:
    # Forward compatibility: a structure from a newer schema still loads.
    restored = ParsedResume.model_validate({"blocks": [], "future_field": 1})
    assert restored.blocks == []
