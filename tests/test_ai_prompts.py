"""Tests for the Jinja2 prompt template library in :mod:`atlas.ai.prompts`."""

from __future__ import annotations

import pytest
from jinja2 import UndefinedError

from atlas.ai.prompts import (
    PARSE_JOB_POSTING_PROMPT_VERSION,
    SCORE_FIT_PROMPT_VERSION,
    SELECT_AND_REWORD_PROMPT_VERSION,
    PromptNotFoundError,
    RenderedPrompt,
    render_prompt,
)


def test_render_parse_job_posting_templates() -> None:
    rendered = render_prompt(
        "parse_job_posting",
        PARSE_JOB_POSTING_PROMPT_VERSION,
        url="https://jobs.example.com/1",
        page_text="Senior Backend Engineer at Acme.",
    )
    assert isinstance(rendered, RenderedPrompt)
    assert rendered.task == "parse_job_posting"
    assert rendered.version == PARSE_JOB_POSTING_PROMPT_VERSION
    # The system prompt sets the extraction role; the user prompt carries context.
    assert "job-posting parser" in rendered.system
    assert "https://jobs.example.com/1" in rendered.user
    assert "Senior Backend Engineer at Acme." in rendered.user


def test_render_score_fit_templates() -> None:
    rendered = render_prompt(
        "score_fit",
        SCORE_FIT_PROMPT_VERSION,
        title="Backend Engineer",
        company="Acme",
        location="Remote",
        remote_type="remote",
        employment_type="full-time",
        seniority="senior",
        salary={"min": 150000},
        keywords=["python"],
        requirements={"must": ["Python"]},
        description="Build reliable services.",
        preferences={"target_roles": ["Backend Engineer"]},
        resume_summary="Summary:\n- Shipped a distributed queue",
        signals={"salary": "within", "location": "match"},
    )
    assert isinstance(rendered, RenderedPrompt)
    assert rendered.task == "score_fit"
    assert rendered.version == SCORE_FIT_PROMPT_VERSION
    # The system prompt sets the assessor role; the user prompt carries context.
    assert "job-fit assessor" in rendered.system
    assert "Backend Engineer" in rendered.user
    assert "Shipped a distributed queue" in rendered.user
    assert "within" in rendered.user


def test_missing_context_variable_raises() -> None:
    # StrictUndefined: a template var the caller omits fails loudly at render.
    with pytest.raises(UndefinedError):
        render_prompt("parse_job_posting", PARSE_JOB_POSTING_PROMPT_VERSION, url="only-url")


def test_missing_score_fit_context_variable_raises() -> None:
    # StrictUndefined applies to score_fit too — an omitted var fails at render.
    with pytest.raises(UndefinedError):
        render_prompt("score_fit", SCORE_FIT_PROMPT_VERSION, title="only-title")


def test_render_select_and_reword_templates() -> None:
    rendered = render_prompt(
        "select_and_reword",
        SELECT_AND_REWORD_PROMPT_VERSION,
        title="Backend Engineer",
        company="Globex",
        location="Remote",
        seniority="senior",
        keywords=["python"],
        requirements={"must": ["Python"]},
        description="Build reliable services.",
        emphasis=["distributed systems"],
        honesty_level="light_inference",
        blocks="[blk_a] (experience) Led the platform team",
    )
    assert isinstance(rendered, RenderedPrompt)
    assert rendered.task == "select_and_reword"
    assert "resume tailor" in rendered.system
    assert "light_inference" in rendered.user
    assert "[blk_a] (experience)" in rendered.user
    assert "distributed systems" in rendered.user


def test_missing_select_and_reword_context_variable_raises() -> None:
    with pytest.raises(UndefinedError):
        render_prompt("select_and_reword", SELECT_AND_REWORD_PROMPT_VERSION, title="only-title")


def test_unknown_task_raises_prompt_not_found() -> None:
    with pytest.raises(PromptNotFoundError, match="no_such_task"):
        render_prompt("no_such_task", 1)


def test_unknown_version_raises_prompt_not_found() -> None:
    with pytest.raises(PromptNotFoundError, match="version 99"):
        render_prompt("parse_job_posting", 99)
