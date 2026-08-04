"""Tests for the view-model mapping in :mod:`atlas.coverletter.context`."""

from __future__ import annotations

from atlas.coverletter.context import build_cover_letter_context
from atlas.coverletter.structure import CoverLetterDraft


def test_build_context_assembles_hook_and_body_into_paragraphs() -> None:
    draft = CoverLetterDraft(
        greeting="Dear Hiring Manager,",
        hook="I am excited to apply.",
        body_paragraphs=["I led a team.", "I know Python."],
        closing="Sincerely,",
    )
    context = build_cover_letter_context(
        draft,
        name="Sam Lee",
        contact_lines=["sam@example.com"],
        company="Globex",
        date="August 4, 2026",
    )
    assert context.name == "Sam Lee"
    assert context.signoff_name == "Sam Lee"
    assert context.company == "Globex"
    assert context.date == "August 4, 2026"
    assert context.greeting == "Dear Hiring Manager,"
    # The hook leads, then the body paragraphs, in order.
    assert context.paragraphs == ["I am excited to apply.", "I led a team.", "I know Python."]
    assert context.closing == "Sincerely,"


def test_build_context_drops_blank_paragraphs() -> None:
    draft = CoverLetterDraft(hook="   ", body_paragraphs=["Real paragraph.", ""])
    context = build_cover_letter_context(
        draft, name="Sam", contact_lines=[], company="Acme", date="today"
    )
    assert context.paragraphs == ["Real paragraph."]
