"""Tests for the render/open display in :mod:`atlas.cli.materials`."""

from __future__ import annotations

from rich.console import RenderableType

from atlas.cli.console import console
from atlas.cli.materials import render_open_outcome, render_rerender_outcome
from atlas.materials.service import OpenOutcome, RerenderOutcome


def _render(renderable: RenderableType) -> str:
    with console.capture() as capture:
        console.print(renderable)
    return capture.get()


def test_render_rerender_outcome_shows_both_paths() -> None:
    outcome = RerenderOutcome(
        application_id=3,
        resume_path="/data/renders/r.pdf",
        cover_letter_path="/data/renders/c.pdf",
    )
    text = _render(render_rerender_outcome(outcome))
    assert "3" in text
    assert "r.pdf" in text
    assert "c.pdf" in text


def test_render_rerender_outcome_marks_missing_material() -> None:
    outcome = RerenderOutcome(
        application_id=3, resume_path="/data/renders/r.pdf", cover_letter_path=None
    )
    text = _render(render_rerender_outcome(outcome))
    assert "r.pdf" in text
    assert "—" in text  # the absent cover letter


def test_render_open_outcome_lists_opened() -> None:
    outcome = OpenOutcome(application_id=3, opened=["/data/renders/r.pdf", "/data/renders/c.pdf"])
    text = _render(render_open_outcome(outcome))
    assert "r.pdf" in text
    assert "c.pdf" in text


def test_render_open_outcome_nothing_to_open() -> None:
    outcome = OpenOutcome(application_id=3, opened=[])
    text = _render(render_open_outcome(outcome))
    assert "Nothing to open" in text
