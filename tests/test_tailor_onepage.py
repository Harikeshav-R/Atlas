"""Tests for the one-page render-measure-trim loop in :mod:`atlas.tailor.onepage`."""

from __future__ import annotations

from atlas.render.structure import ResumeContext, ResumeEntry, ResumeSection
from atlas.tailor.onepage import pack_to_one_page
from tests.conftest import FakePdfRenderer, SequencedPdfRenderer


def _context(entries_per_section: list[int]) -> ResumeContext:
    sections = [
        ResumeSection(
            heading=f"S{i}",
            entries=[ResumeEntry(lines=[f"s{i}e{j}"]) for j in range(count)],
        )
        for i, count in enumerate(entries_per_section)
    ]
    return ResumeContext(name="Sam", sections=sections)


def test_already_one_page_does_not_trim() -> None:
    renderer = FakePdfRenderer(page_count=1)
    packed = pack_to_one_page(_context([2, 2]), renderer=renderer, theme="jakes-resume")
    assert packed.result.page_count == 1
    assert packed.trimmed == 0
    assert len(renderer.html_calls) == 1  # rendered once, no re-render


def test_overflow_then_converges() -> None:
    # First render overflows (2 pages), one trim, second render fits (1 page).
    renderer = SequencedPdfRenderer([2, 1])
    packed = pack_to_one_page(_context([2, 2]), renderer=renderer, theme="jakes-resume")
    assert packed.result.page_count == 1
    assert packed.trimmed == 1
    # One entry was removed from the last section.
    assert sum(len(s.entries) for s in packed.context.sections) == 3


def test_trim_removes_emptied_section() -> None:
    # Last section has a single entry; trimming it drops the whole section.
    renderer = SequencedPdfRenderer([2, 1])
    packed = pack_to_one_page(_context([2, 1]), renderer=renderer, theme="jakes-resume")
    assert packed.trimmed == 1
    assert [s.heading for s in packed.context.sections] == ["S0"]


def test_never_converges_stops_at_cap_or_empty() -> None:
    # Always 2 pages: trims every entry, then stops when nothing remains to trim.
    renderer = SequencedPdfRenderer([2])
    packed = pack_to_one_page(_context([1, 1]), renderer=renderer, theme="jakes-resume")
    assert packed.result.page_count == 2  # best effort — never fit
    assert packed.trimmed == 2  # both entries trimmed
    assert packed.context.sections == []


def test_cap_bounds_iterations() -> None:
    renderer = SequencedPdfRenderer([2])
    packed = pack_to_one_page(_context([10]), renderer=renderer, theme="jakes-resume", max_iters=3)
    assert packed.trimmed == 3  # stopped at the cap, not all 10 entries


def test_trim_skips_a_trailing_empty_section() -> None:
    # A context whose last section has no entries: the trimmer skips it and trims
    # the earlier non-empty section instead.
    context = ResumeContext(
        name="Sam",
        sections=[
            ResumeSection(heading="S0", entries=[ResumeEntry(lines=["keep"])]),
            ResumeSection(heading="S1", entries=[]),
        ],
    )
    renderer = SequencedPdfRenderer([2, 1])
    packed = pack_to_one_page(context, renderer=renderer, theme="jakes-resume")
    assert packed.trimmed == 1
    # The earlier section was trimmed to empty and dropped; only the trailing
    # (already-empty) section remains — no non-empty content is left.
    assert [s.heading for s in packed.context.sections] == ["S1"]
    assert all(not s.entries for s in packed.context.sections)


def test_enforce_false_renders_once_without_trimming() -> None:
    renderer = FakePdfRenderer(page_count=2)
    packed = pack_to_one_page(
        _context([3, 3]), renderer=renderer, theme="jakes-resume", enforce_one_page=False
    )
    assert packed.result.page_count == 2
    assert packed.trimmed == 0
    assert len(renderer.html_calls) == 1
