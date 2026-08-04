"""Versioned Jinja2 prompt templates for Atlas's AI tasks (PROJECT.md §7, §18.1).

Each AI task is a versioned pair of Jinja2 templates (``system.jinja`` +
``user.jinja``) under ``templates/<task>/v<version>/``, rendered via
:func:`render_prompt` into a :class:`RenderedPrompt`. Storing prompts as versioned
templates (rather than inline Python constants) is the locked decision in
PROJECT.md §18.1: a task's wording can evolve under a new version directory while
old versions remain reproducible, and each call records the version it used.

Callers import a task's current version as a module constant (e.g.
:data:`PARSE_JOB_POSTING_PROMPT_VERSION`) and pass it explicitly, so bumping a
prompt is a one-line, greppable change.
"""

from __future__ import annotations

from atlas.ai.prompts.errors import PromptError, PromptNotFoundError
from atlas.ai.prompts.loader import RenderedPrompt, render_prompt

__all__ = [
    "PARSE_JOB_POSTING_PROMPT_VERSION",
    "SCORE_FIT_PROMPT_VERSION",
    "SELECT_AND_REWORD_PROMPT_VERSION",
    "PromptError",
    "PromptNotFoundError",
    "RenderedPrompt",
    "render_prompt",
]

#: The prompt-template version the ``parse_job_posting`` task currently uses.
PARSE_JOB_POSTING_PROMPT_VERSION = 1

#: The prompt-template version the ``score_fit`` task currently uses.
SCORE_FIT_PROMPT_VERSION = 1

#: The prompt-template version the ``select_and_reword`` task currently uses.
SELECT_AND_REWORD_PROMPT_VERSION = 1
