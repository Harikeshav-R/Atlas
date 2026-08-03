"""Loader for Atlas's versioned Jinja2 AI-prompt templates (PROJECT.md §7, §18.1).

Each AI task (``parse_job_posting``, ``score_fit``, …) has a versioned pair of
Jinja2 templates — ``system.jinja`` and ``user.jinja`` — laid out under
``templates/<task>/v<version>/``. :func:`render_prompt` renders a task's templates
with a context and returns a :class:`RenderedPrompt`, so callers build an
:class:`~atlas.ai.base.LLMRequest` from real templates rather than inline Python
strings (the locked decision in PROJECT.md §18.1).

The environment uses :class:`~jinja2.StrictUndefined`, so a template referencing a
context variable the caller forgot to pass fails loudly at render time rather than
silently emitting an empty string into a prompt. The templates ship inside the
package (hatchling includes the whole ``src/atlas`` tree in the wheel, as it does
for the Alembic migration files).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, StrictUndefined, TemplateNotFound
from pydantic import BaseModel

from atlas.ai.prompts.errors import PromptNotFoundError

__all__ = ["RenderedPrompt", "render_prompt"]

#: The bundled templates directory (shipped in the wheel with the package).
_TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"

#: One shared Jinja2 environment. ``StrictUndefined`` turns a missing context
#: variable into an error; ``autoescape`` is off because prompts are plain text,
#: not HTML; ``trim_blocks``/``lstrip_blocks`` keep whitespace predictable.
_ENV = Environment(
    loader=FileSystemLoader(str(_TEMPLATES_DIR)),
    undefined=StrictUndefined,
    trim_blocks=True,
    lstrip_blocks=True,
    autoescape=False,
    keep_trailing_newline=False,
)


class RenderedPrompt(BaseModel):
    """A task's rendered system and user prompts, with their provenance.

    Attributes:
        task: The AI task name (e.g. ``"parse_job_posting"``).
        version: The prompt-template version that produced this.
        system: The rendered system prompt.
        user: The rendered user prompt.
    """

    task: str
    version: int
    system: str
    user: str


def render_prompt(task: str, version: int, /, **context: Any) -> RenderedPrompt:
    """Render a task's versioned ``system``/``user`` templates with ``context``.

    Args:
        task: The AI task name; selects the ``templates/<task>/`` directory.
        version: The template version; selects the ``v<version>/`` directory.
        **context: Variables made available to both templates. A variable a
            template references but the caller omits raises (``StrictUndefined``).

    Returns:
        The :class:`RenderedPrompt` for ``task`` at ``version``.

    Raises:
        PromptNotFoundError: If the task/version has no ``system.jinja`` or
            ``user.jinja`` template.
    """
    prefix = f"{task}/v{version}"
    try:
        system_template = _ENV.get_template(f"{prefix}/system.jinja")
        user_template = _ENV.get_template(f"{prefix}/user.jinja")
    except TemplateNotFound as exc:
        raise PromptNotFoundError(
            f"No prompt template for task {task!r} version {version}."
        ) from exc
    return RenderedPrompt(
        task=task,
        version=version,
        system=system_template.render(**context),
        user=user_template.render(**context),
    )
