"""Tests for the deterministic Markdown parser in :mod:`atlas.resume.parser`."""

from __future__ import annotations

import pytest

from atlas.resume.parser import normalize_markdown, parse_markdown
from atlas.resume.structure import BlockType, ParsedBlock, ParsedResume

_SAMPLE = """\
# Sam Carter
sam@example.com | https://sam.dev

## Summary

Backend engineer who ships.

## Experience

### Acme — Senior Engineer (2020-2024)

- Cut latency by 30%
- Led a team of four

## Skills

- Python, Rust
- Postgres

## Certifications

- AWS Solutions Architect

## Publications

- A paper on caching

## Links

- https://github.com/sam

## Hobbies

- Bouldering
"""


def _by_type(resume: ParsedResume, block_type: BlockType) -> list[ParsedBlock]:
    return [block for block in resume.blocks if block.type is block_type]


def test_parses_all_sections_into_typed_blocks() -> None:
    resume = parse_markdown(_SAMPLE)
    # The ``#`` title and the contact line under it are contact blocks.
    contact_texts = [block.text for block in _by_type(resume, BlockType.CONTACT)]
    assert contact_texts == ["Sam Carter", "sam@example.com | https://sam.dev"]
    assert [block.text for block in _by_type(resume, BlockType.SUMMARY)] == [
        "Backend engineer who ships."
    ]
    # A ``###`` sub-heading and the bullets under it all belong to the section.
    assert [block.text for block in _by_type(resume, BlockType.EXPERIENCE)] == [
        "Acme — Senior Engineer (2020-2024)",
        "Cut latency by 30%",
        "Led a team of four",
    ]
    assert [block.text for block in _by_type(resume, BlockType.SKILL)] == [
        "Python, Rust",
        "Postgres",
    ]
    assert _by_type(resume, BlockType.CERTIFICATION)[0].text == "AWS Solutions Architect"
    assert _by_type(resume, BlockType.PUBLICATION)[0].text == "A paper on caching"
    assert _by_type(resume, BlockType.LINK)[0].text == "https://github.com/sam"
    # An unrecognized ``## Hobbies`` section falls back to OTHER.
    assert _by_type(resume, BlockType.OTHER)[0].text == "Bouldering"


def test_positions_are_sequential_in_document_order() -> None:
    resume = parse_markdown(_SAMPLE)
    assert [block.position for block in resume.blocks] == list(range(len(resume.blocks)))


@pytest.mark.parametrize(
    ("heading", "expected"),
    [
        ("## Work History", BlockType.EXPERIENCE),
        ("## Employment", BlockType.EXPERIENCE),
        ("## Projects", BlockType.PROJECT),
        ("## Technical Skills", BlockType.SKILL),
        ("## Education", BlockType.EDUCATION),
        ("## Objective", BlockType.SUMMARY),
        ("## About Me", BlockType.SUMMARY),
        ("## Professional Profile", BlockType.SUMMARY),
        ("## Contact", BlockType.CONTACT),
        ("## Something Else", BlockType.OTHER),
    ],
)
def test_section_keyword_classification(heading: str, expected: BlockType) -> None:
    resume = parse_markdown(f"{heading}\n\n- an item")
    assert resume.blocks[-1].type is expected


def test_paragraphs_join_multiple_lines() -> None:
    resume = parse_markdown("## Summary\n\nLine one\nline two\n\nSecond paragraph")
    summary = [block.text for block in resume.blocks]
    assert summary == ["Line one\nline two", "Second paragraph"]


def test_headingless_input_is_captured_best_effort() -> None:
    resume = parse_markdown("Just some text\n\nAnd more text")
    assert [block.type for block in resume.blocks] == [BlockType.CONTACT, BlockType.CONTACT]
    assert [block.text for block in resume.blocks] == ["Just some text", "And more text"]


@pytest.mark.parametrize("source", ["", "   \n\n\t\n"])
def test_empty_input_yields_no_blocks(source: str) -> None:
    assert parse_markdown(source).blocks == []


def test_duplicate_bullets_get_distinct_stable_ids() -> None:
    resume = parse_markdown("## Experience\n\n- Shipped it\n- Shipped it")
    first, second = resume.blocks
    assert first.text == second.text
    assert first.content_id != second.content_id
    # Re-parsing the same source reproduces the same ids (stability).
    again = parse_markdown("## Experience\n\n- Shipped it\n- Shipped it")
    assert [block.content_id for block in again.blocks] == [first.content_id, second.content_id]


def test_content_ids_are_position_independent() -> None:
    first = parse_markdown("## Skills\n\n- Python\n- Rust")
    reordered = parse_markdown("## Skills\n\n- Rust\n- Python")
    assert {block.content_id for block in first.blocks} == {
        block.content_id for block in reordered.blocks
    }


def test_fallback_used_for_headingless_content() -> None:
    sentinel = ParsedResume(
        blocks=[ParsedBlock(type=BlockType.OTHER, content_id="blk_ai", position=0, text="ai")]
    )
    calls: list[str] = []

    def fake_extractor(markdown: str) -> ParsedResume:
        calls.append(markdown)
        return sentinel

    result = parse_markdown("no headings here", fallback=fake_extractor)
    assert result is sentinel
    assert calls == ["no headings here"]


def test_fallback_not_used_for_structured_input() -> None:
    def fake_extractor(markdown: str) -> ParsedResume:  # pragma: no cover - must not run
        raise AssertionError("fallback should not be consulted for structured input")

    resume = parse_markdown("## Skills\n\n- Python", fallback=fake_extractor)
    assert resume.blocks[0].type is BlockType.SKILL


def test_fallback_not_used_for_empty_input() -> None:
    def fake_extractor(markdown: str) -> ParsedResume:  # pragma: no cover - must not run
        raise AssertionError("fallback should not be consulted for empty input")

    assert parse_markdown("   ", fallback=fake_extractor).blocks == []


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("\r\n\r\nHello  \r\nWorld\r\n\r\n", "Hello\nWorld"),
        # Only trailing whitespace is stripped; leading indentation is preserved.
        ("  line with trailing   \n", "  line with trailing"),
        ("a\n\n\nb", "a\n\n\nb"),
        ("", ""),
        ("\n\n\n", ""),
    ],
)
def test_normalize_markdown(raw: str, expected: str) -> None:
    assert normalize_markdown(raw) == expected
