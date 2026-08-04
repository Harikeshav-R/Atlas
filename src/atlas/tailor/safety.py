"""Deterministic post-generation safety nets for tailoring (PROJECT.md §5.7 step 6).

These are non-LLM backstops that run regardless of the honesty level. The one
implemented here guards a specific, known LLM failure: models silently drop or
coarsen **month precision on employment dates** when rewording. :func:`restore_dates`
finds date tokens (``Jan 2024``, ``01/2024``, ``2020-2026`` …) in each source block
and, keyed by ``content_id``, re-appends any that the reworded text dropped — so a
tailored bullet never loses a real date. Pure and I/O-free (regex only).
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from atlas.db.models import ResumeBlock
    from atlas.tailor.structure import TailoredItem

__all__ = ["extract_dates", "restore_dates"]

_MONTHS = (
    "jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec|"
    "january|february|march|april|may|june|july|august|september|october|november|december"
)

#: Date tokens Atlas preserves: "Month YYYY", "MM/YYYY", or a bare 4-digit year.
#: Matched case-insensitively; the longest, most specific forms come first.
_DATE_PATTERN = re.compile(
    rf"(?:{_MONTHS})\.?\s+\d{{4}}"  # Month YYYY (optional abbreviation dot)
    r"|\d{1,2}/\d{4}"  # MM/YYYY
    r"|\b\d{4}\b",  # bare year
    re.IGNORECASE,
)


def extract_dates(text: str) -> list[str]:
    """Return the date tokens found in ``text``, in order, de-duplicated."""
    seen: list[str] = []
    for match in _DATE_PATTERN.findall(text):
        if match not in seen:
            seen.append(match)
    return seen


def restore_dates(
    items: list[TailoredItem], source_blocks: list[ResumeBlock]
) -> list[TailoredItem]:
    """Re-append source dates the reworded text dropped, keyed by content id.

    For each item whose source block contained date tokens, any token missing
    from the item's ``final_text`` (case-insensitively) is appended in parentheses
    so a real employment date is never lost to rewording (§5.7 step 6). Returns
    new :class:`~atlas.tailor.structure.TailoredItem` instances; the inputs are not
    mutated.

    Args:
        items: The tailored items (post-rework).
        source_blocks: The master-resume blocks (the source of truth for dates).

    Returns:
        The items with any dropped dates restored.
    """
    by_id = {block.content_id: block for block in source_blocks}
    restored: list[TailoredItem] = []
    for item in items:
        source = by_id.get(item.content_id)
        if source is None:
            restored.append(item)
            continue
        source_dates = extract_dates(source.text)
        present = item.final_text.lower()
        missing = [date for date in source_dates if date.lower() not in present]
        if not missing:
            restored.append(item)
            continue
        suffix = " (" + ", ".join(missing) + ")"
        restored.append(item.model_copy(update={"final_text": item.final_text.rstrip() + suffix}))
    return restored
