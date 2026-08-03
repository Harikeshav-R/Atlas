"""Tests for the Jinja2 prompt template library in :mod:`atlas.ai.prompts`."""

from __future__ import annotations

import pytest
from jinja2 import UndefinedError

from atlas.ai.prompts import (
    PARSE_JOB_POSTING_PROMPT_VERSION,
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


def test_missing_context_variable_raises() -> None:
    # StrictUndefined: a template var the caller omits fails loudly at render.
    with pytest.raises(UndefinedError):
        render_prompt("parse_job_posting", PARSE_JOB_POSTING_PROMPT_VERSION, url="only-url")


def test_unknown_task_raises_prompt_not_found() -> None:
    with pytest.raises(PromptNotFoundError, match="no_such_task"):
        render_prompt("no_such_task", 1)


def test_unknown_version_raises_prompt_not_found() -> None:
    with pytest.raises(PromptNotFoundError, match="version 99"):
        render_prompt("parse_job_posting", 99)
