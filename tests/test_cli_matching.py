"""Tests for the fit-score rendering logic in :mod:`atlas.cli.matching`."""

from __future__ import annotations

import pytest
from rich.console import RenderableType

from atlas.cli.console import console
from atlas.cli.matching import render_score, verdict_style
from atlas.matching.service import ScoreOutcome
from atlas.matching.structure import DeterministicSignals, SalaryFit, SignalStatus


def _render(renderable: RenderableType) -> str:
    with console.capture() as capture:
        console.print(renderable)
    return capture.get()


def _outcome(
    *,
    verdict: str = "good",
    matched: list[str] | None = None,
    gaps: list[str] | None = None,
    dealbreakers: list[str] | None = None,
    rationale: str = "Good overlap.",
    signals: DeterministicSignals | None = None,
) -> ScoreOutcome:
    return ScoreOutcome(
        match_score_id=1,
        posting_id=7,
        title="Backend Engineer",
        company="Acme",
        score=78,
        verdict=verdict,
        salary_fit="within",
        rationale=rationale,
        matched_strengths=matched if matched is not None else ["Python"],
        gaps=gaps if gaps is not None else ["Kubernetes"],
        dealbreaker_hits=dealbreakers if dealbreakers is not None else [],
        signals=signals
        if signals is not None
        else DeterministicSignals(
            salary=SalaryFit.WITHIN,
            location=SignalStatus.MATCH,
            work_auth=SignalStatus.UNKNOWN,
            dealbreakers=[],
        ),
    )


@pytest.mark.parametrize(
    ("verdict", "expected"),
    [
        ("strong", "success"),
        ("good", "ok"),
        ("stretch", "warning"),
        ("weak", "bad"),
        ("mystery", "muted"),  # unknown verdict falls back to muted
    ],
)
def test_verdict_style(verdict: str, expected: str) -> None:
    assert verdict_style(verdict) == expected


def test_render_score_shows_core_fields() -> None:
    text = _render(render_score(_outcome()))
    assert "Backend Engineer" in text
    assert "Acme" in text
    assert "78/100" in text
    assert "good" in text
    assert "Good overlap." in text
    assert "Python" in text
    assert "Kubernetes" in text


def test_render_score_empty_lists_and_blank_rationale() -> None:
    outcome = _outcome(
        matched=[],
        gaps=[],
        dealbreakers=[],
        rationale="",
        signals=DeterministicSignals(dealbreakers=[]),
    )
    text = _render(render_score(outcome))
    # Empty sections and a blank rationale render the em-dash placeholder.
    assert "—" in text
    assert "Matched strengths" in text


def test_render_score_shows_dealbreaker_hits() -> None:
    outcome = _outcome(
        dealbreakers=["on-call"],
        signals=DeterministicSignals(dealbreakers=["on-call"]),
    )
    text = _render(render_score(outcome))
    assert "on-call" in text
