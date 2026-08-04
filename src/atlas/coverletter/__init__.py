"""Generate a cover letter for a job posting (PROJECT.md §5.8, §7).

Given a stored :class:`~atlas.db.models.JobPosting`, the active profile, and the
candidate's material (the tailored resume's selections if present, else the master
resume), Atlas drafts a truth-anchored cover letter: an honesty-governed AI pass
produces a structured letter (greeting, hook, body paragraphs, close) grounded in
real content, which is rendered to a PDF matching the resume styling via
:mod:`atlas.render` and persisted append-only per application.

This package owns the letter draft model (:mod:`atlas.coverletter.structure`), the
AI write pass (:mod:`atlas.coverletter.ai_write`), the render view-model mapping
(:mod:`atlas.coverletter.context`), persistence over an open session
(:mod:`atlas.coverletter.repository`), the generation orchestration
(:mod:`atlas.coverletter.service`), and the package error hierarchy
(:mod:`atlas.coverletter.errors`).
"""

from __future__ import annotations

from atlas.coverletter.ai_write import write_cover_letter
from atlas.coverletter.context import build_cover_letter_context
from atlas.coverletter.errors import (
    CoverLetterError,
    CoverLetterOutputError,
    NoActiveProfileError,
    NoMasterResumeError,
)
from atlas.coverletter.repository import create_cover_letter, get_latest_cover_letter
from atlas.coverletter.service import CoverLetterOutcome, write_application_cover_letter
from atlas.coverletter.structure import CoverLetterDraft

__all__ = [
    "CoverLetterDraft",
    "CoverLetterError",
    "CoverLetterOutcome",
    "CoverLetterOutputError",
    "NoActiveProfileError",
    "NoMasterResumeError",
    "build_cover_letter_context",
    "create_cover_letter",
    "get_latest_cover_letter",
    "write_application_cover_letter",
    "write_cover_letter",
]
