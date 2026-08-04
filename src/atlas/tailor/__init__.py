"""Tailor a resume to a job posting (PROJECT.md §5.7, §7).

Given a stored :class:`~atlas.db.models.JobPosting`, the active profile's tailoring
emphasis, and the master resume (content-ID'd blocks), Atlas produces a
truth-anchored, one-page tailored resume: an honesty-governed AI pass selects and
rewords the most relevant blocks (each tracing back to a source block by
``content_id``), a deterministic safety net restores month precision on dates the
model may have dropped, and a render-measure-trim loop packs the result onto one
page using :mod:`atlas.render`.

This package owns the tailoring output models (:mod:`atlas.tailor.structure`), the
AI select-and-reword pass (:mod:`atlas.tailor.ai_tailor`), the block mapping
(:mod:`atlas.tailor.blocks`), the deterministic safety nets
(:mod:`atlas.tailor.safety`), the one-page packing loop
(:mod:`atlas.tailor.onepage`), persistence over an open session
(:mod:`atlas.tailor.repository`), the tailoring orchestration
(:mod:`atlas.tailor.service`), and the package error hierarchy
(:mod:`atlas.tailor.errors`).
"""

from __future__ import annotations

from atlas.tailor.ai_tailor import select_and_reword
from atlas.tailor.blocks import render_blocks, tag_blocks_for_prompt
from atlas.tailor.errors import (
    ApplicationNotFoundError,
    NoActiveProfileError,
    NoMasterResumeError,
    TailoringError,
    TailoringOutputError,
)
from atlas.tailor.onepage import PackResult, pack_to_one_page
from atlas.tailor.repository import (
    create_tailored_resume,
    get_application,
    get_latest_tailored_resume,
    get_or_create_application,
)
from atlas.tailor.safety import extract_dates, restore_dates
from atlas.tailor.service import TailorOutcome, tailor_posting
from atlas.tailor.structure import TailoredItem, TailoredResume

__all__ = [
    "ApplicationNotFoundError",
    "NoActiveProfileError",
    "NoMasterResumeError",
    "PackResult",
    "TailorOutcome",
    "TailoredItem",
    "TailoredResume",
    "TailoringError",
    "TailoringOutputError",
    "create_tailored_resume",
    "extract_dates",
    "get_application",
    "get_latest_tailored_resume",
    "get_or_create_application",
    "pack_to_one_page",
    "render_blocks",
    "restore_dates",
    "select_and_reword",
    "tag_blocks_for_prompt",
    "tailor_posting",
]
