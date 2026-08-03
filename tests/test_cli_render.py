"""Tests for the render-outcome rendering logic in :mod:`atlas.cli.render`."""

from __future__ import annotations

from rich.console import RenderableType

from atlas.cli.console import console
from atlas.cli.render import render_render_outcome
from atlas.render.service import RenderOutcome


def _render(renderable: RenderableType) -> str:
    with console.capture() as capture:
        console.print(renderable)
    return capture.get()


def _outcome(*, page_count: int, one_page: bool) -> RenderOutcome:
    return RenderOutcome(
        path="/data/renders/Sam_Lee__resume__v1.pdf",
        page_count=page_count,
        one_page=one_page,
        version=1,
        theme="jakes-resume",
    )


def test_render_outcome_one_page_shows_path_and_no_warning() -> None:
    text = _render(render_render_outcome(_outcome(page_count=1, one_page=True)))
    assert "Sam_Lee__resume__v1.pdf" in text
    assert "jakes-resume" in text
    assert "v1" in text
    assert "exceeds one page" not in text


def test_render_outcome_overflow_shows_warning() -> None:
    text = _render(render_render_outcome(_outcome(page_count=2, one_page=False)))
    assert "2 pages" in text
    assert "exceeds one page" in text
