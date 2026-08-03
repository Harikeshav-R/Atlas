"""Tests for the tailoring models in :mod:`atlas.tailor.structure`."""

from __future__ import annotations

from atlas.tailor.structure import TailoredItem, TailoredResume


def test_tailored_item_defaults() -> None:
    item = TailoredItem()
    assert item.content_id == ""
    assert item.final_text == ""
    assert item.included is True


def test_tailored_resume_defaults() -> None:
    tailored = TailoredResume()
    assert tailored.items == []
    assert tailored.gaps == []
    assert tailored.summary_rationale == ""


def test_tailored_resume_validates_from_dict() -> None:
    tailored = TailoredResume.model_validate(
        {
            "items": [
                {"content_id": "blk_a", "block_type": "experience", "final_text": "Led team"}
            ],
            "gaps": ["Kubernetes"],
            "summary_rationale": "focus on platform",
        }
    )
    assert tailored.items[0].content_id == "blk_a"
    assert tailored.items[0].included is True
    assert tailored.gaps == ["Kubernetes"]


def test_tailored_resume_ignores_unknown_keys() -> None:
    tailored = TailoredResume.model_validate({"items": [], "unexpected": "field"})
    assert tailored.items == []
