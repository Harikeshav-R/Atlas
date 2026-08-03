"""Tests for the tailor-outcome rendering logic in :mod:`atlas.cli.tailor`."""

from __future__ import annotations

from rich.console import RenderableType

from atlas.cli.console import console
from atlas.cli.tailor import render_tailor_outcome
from atlas.tailor.service import TailorOutcome


def _render(renderable: RenderableType) -> str:
    with console.capture() as capture:
        console.print(renderable)
    return capture.get()


def _outcome(
    *, one_page: bool = True, page_count: int = 1, gaps: list[str] | None = None
) -> TailorOutcome:
    return TailorOutcome(
        application_id=3,
        tailored_resume_id=5,
        version=1,
        posting_id=7,
        title="Backend Engineer",
        company="Globex",
        path="/data/renders/Sam__Globex__tailored.pdf",
        page_count=page_count,
        one_page=one_page,
        included_count=6,
        trimmed=0,
        gaps=gaps if gaps is not None else ["Kubernetes"],
    )


def test_render_tailor_outcome_one_page() -> None:
    text = _render(render_tailor_outcome(_outcome()))
    assert "Backend Engineer" in text
    assert "Globex" in text
    assert "Sam__Globex__tailored.pdf" in text
    assert "Kubernetes" in text  # gaps shown
    assert "could not trim" not in text


def test_render_tailor_outcome_overflow_warns() -> None:
    text = _render(render_tailor_outcome(_outcome(one_page=False, page_count=2)))
    assert "2 pages" in text
    assert "could not trim" in text


def test_render_tailor_outcome_no_gaps() -> None:
    text = _render(render_tailor_outcome(_outcome(gaps=[])))
    assert "Gaps:" in text
    assert "none" in text
