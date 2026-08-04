"""Tests for the cover-letter models in :mod:`atlas.coverletter.structure`."""

from __future__ import annotations

from atlas.coverletter.structure import CoverLetterDraft


def test_cover_letter_draft_defaults() -> None:
    draft = CoverLetterDraft()
    assert draft.greeting == ""
    assert draft.hook == ""
    assert draft.body_paragraphs == []
    assert draft.closing == ""
    assert draft.gaps == []


def test_cover_letter_draft_validates_from_dict() -> None:
    draft = CoverLetterDraft.model_validate(
        {
            "greeting": "Dear Hiring Manager,",
            "hook": "I am writing to apply.",
            "body_paragraphs": ["Para one.", "Para two."],
            "closing": "Sincerely,",
            "gaps": ["Kubernetes"],
        }
    )
    assert draft.hook == "I am writing to apply."
    assert draft.body_paragraphs == ["Para one.", "Para two."]
    assert draft.gaps == ["Kubernetes"]


def test_cover_letter_draft_ignores_unknown_keys() -> None:
    draft = CoverLetterDraft.model_validate({"greeting": "Hi", "unexpected": "field"})
    assert draft.greeting == "Hi"
