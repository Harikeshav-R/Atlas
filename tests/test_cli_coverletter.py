"""Tests for the cover-letter display in :mod:`atlas.cli.coverletter`."""

from __future__ import annotations

from rich.console import RenderableType

from atlas.cli.console import console
from atlas.cli.coverletter import render_cover_letter_outcome
from atlas.coverletter.service import CoverLetterOutcome


def _render(renderable: RenderableType) -> str:
    with console.capture() as capture:
        console.print(renderable)
    return capture.get()


def _outcome(
    *,
    one_page: bool = True,
    page_count: int = 1,
    grounded_on: str = "tailored_resume",
    gaps: list[str] | None = None,
) -> CoverLetterOutcome:
    return CoverLetterOutcome(
        application_id=3,
        cover_letter_id=5,
        version=1,
        posting_id=7,
        title="Backend Engineer",
        company="Globex",
        path="/data/renders/Sam__Globex__cover.pdf",
        page_count=page_count,
        one_page=one_page,
        tone="professional",
        grounded_on=grounded_on,
        gaps=gaps if gaps is not None else ["Kubernetes"],
    )


def test_render_cover_letter_one_page() -> None:
    text = _render(render_cover_letter_outcome(_outcome()))
    assert "Backend Engineer" in text
    assert "Sam__Globex__cover.pdf" in text
    assert "tailored resume" in text  # grounding label
    assert "Kubernetes" in text
    assert "consider trimming" not in text


def test_render_cover_letter_overflow_warns() -> None:
    text = _render(render_cover_letter_outcome(_outcome(one_page=False, page_count=2)))
    assert "2 pages" in text
    assert "consider trimming" in text


def test_render_cover_letter_master_resume_grounding_and_no_gaps() -> None:
    text = _render(render_cover_letter_outcome(_outcome(grounded_on="master_resume", gaps=[])))
    assert "master resume" in text
    assert "Gaps:" in text
    assert "none" in text
