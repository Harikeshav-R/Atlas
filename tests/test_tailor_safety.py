"""Tests for the deterministic safety nets in :mod:`atlas.tailor.safety`."""

from __future__ import annotations

from atlas.db.models import ResumeBlock
from atlas.tailor.safety import extract_dates, restore_dates
from atlas.tailor.structure import TailoredItem


def _block(content_id: str, text: str) -> ResumeBlock:
    return ResumeBlock(
        master_resume_id=1, type="experience", content_id=content_id, position=0, text=text
    )


def test_extract_dates_finds_month_year_slash_and_bare_year() -> None:
    assert extract_dates("Acme Jan 2020 - Mar 2026") == ["Jan 2020", "Mar 2026"]
    assert extract_dates("Role 01/2024 to present") == ["01/2024"]
    assert extract_dates("Graduated 2019") == ["2019"]


def test_extract_dates_dedupes() -> None:
    assert extract_dates("2020 and again 2020") == ["2020"]


def test_restore_dates_reappends_dropped_dates() -> None:
    source = [_block("blk_a", "Staff Engineer, Acme Jan 2020 - Mar 2026")]
    items = [TailoredItem(content_id="blk_a", final_text="Led the platform team at Acme")]
    restored = restore_dates(items, source)
    assert restored[0].final_text == "Led the platform team at Acme (Jan 2020, Mar 2026)"


def test_restore_dates_leaves_present_dates_untouched() -> None:
    source = [_block("blk_a", "Acme Jan 2020 - Mar 2026")]
    items = [TailoredItem(content_id="blk_a", final_text="Worked Jan 2020 - Mar 2026 at Acme")]
    restored = restore_dates(items, source)
    assert restored[0].final_text == "Worked Jan 2020 - Mar 2026 at Acme"


def test_restore_dates_no_source_dates_no_change() -> None:
    source = [_block("blk_a", "A skills block with no dates")]
    items = [TailoredItem(content_id="blk_a", final_text="Python, Go")]
    restored = restore_dates(items, source)
    assert restored[0].final_text == "Python, Go"


def test_restore_dates_ignores_items_without_a_source_block() -> None:
    # An item whose id has no matching source block passes through unchanged.
    items = [TailoredItem(content_id="blk_missing", final_text="text")]
    restored = restore_dates(items, [_block("blk_a", "Jan 2020")])
    assert restored[0].final_text == "text"
