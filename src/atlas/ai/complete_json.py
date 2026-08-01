"""Provider-agnostic structured-output contract for the AI layer.

:func:`complete_json` is the single helper every structured AI task calls. It
asks a backend for JSON matching a Pydantic model and recovers from imperfect
output in layers before giving up, per ``docs/PROJECT.md`` §5.1:

1. Read the backend's native structured field and validate it.
2. Extract the first balanced JSON object from the text (handles prose / code
   fences) and validate that.
3. Retry a bounded number of times, nudging temperature up to break a stuck
   deterministic failure.
4. Fall back to a plain prompt that asks for JSON only, and extract from that.
5. Raise :class:`~atlas.ai.base.LLMOutputError`.

These are *content* retries. Transport retries (network/5xx/rate-limit) are a
separate concern owned by the API backend's router and are not handled here.
"""

from __future__ import annotations

import json
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

from atlas.ai.base import LLMOutputError, LLMProvider, LLMRequest

__all__ = ["complete_json"]

T = TypeVar("T", bound=BaseModel)

# Appended to the prompt on the final, schema-free fallback attempt.
_PROMPT_ONLY_INSTRUCTION = (
    "Return ONLY a single JSON object that satisfies the requested structure. "
    "Do not include any explanation, prose, or code fences."
)


def _extract_json(text: str) -> dict[str, Any] | None:
    """Return the first balanced JSON object embedded in ``text``, or ``None``.

    Scans from the first ``{`` and tracks string and escape state so braces and
    quotes inside string values do not throw off the balance count. Returns the
    parsed object once braces balance, or ``None`` if no balanced object is
    found or the balanced span is not valid JSON.
    """
    start = text.find("{")
    if start == -1:
        return None

    depth = 0
    in_string = False
    escaped = False
    for index in range(start, len(text)):
        char = text[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                try:
                    parsed = json.loads(text[start : index + 1])
                except json.JSONDecodeError:
                    return None
                # A balanced ``{...}`` span parses to a JSON object, i.e. a dict.
                return dict(parsed)
    return None


def _temperature_for(base: float | None, attempt: int, step: float) -> float | None:
    """Compute the sampling temperature for a given retry ``attempt``.

    Attempt 0 keeps the caller's temperature unchanged; later attempts escalate
    by ``step`` per attempt (starting from 0.0 when no base was set) to break a
    stuck deterministic failure.
    """
    if attempt == 0:
        return base
    if base is None:
        return step * attempt
    return base + step * attempt


def complete_json(
    provider: LLMProvider,
    request: LLMRequest,
    model_cls: type[T],
    *,
    max_retries: int = 2,
    temperature_step: float = 0.2,
) -> T:
    """Complete ``request`` against ``provider`` and return a validated ``model_cls``.

    Sets ``request.response_schema`` from ``model_cls`` and runs the layered
    recovery described in this module's docstring. The caller's ``request`` is
    never mutated.

    Args:
        provider: The backend to call.
        request: The base request; its schema and temperature are adjusted on
            copies per attempt.
        model_cls: The Pydantic model the response must validate against.
        max_retries: Extra attempts beyond the first before the prompt-only
            fallback (so total structured attempts is ``max_retries + 1``).
        temperature_step: Amount to raise temperature per retry attempt.

    Returns:
        An instance of ``model_cls`` parsed from the backend's output.

    Raises:
        LLMOutputError: If no attempt, nor the prompt-only fallback, yields
            output that validates against ``model_cls``.
    """
    schema = model_cls.model_json_schema()
    base_temperature = request.temperature
    last_error: ValidationError | None = None

    def _validated(candidate: dict[str, Any] | None) -> T | None:
        nonlocal last_error
        if candidate is None:
            return None
        try:
            return model_cls.model_validate(candidate)
        except ValidationError as exc:
            last_error = exc
            return None

    for attempt in range(max_retries + 1):
        structured_request = request.model_copy(
            update={
                "response_schema": schema,
                "temperature": _temperature_for(base_temperature, attempt, temperature_step),
            }
        )
        response = provider.complete(structured_request)
        native = _validated(response.structured)
        if native is not None:
            return native
        extracted = _validated(_extract_json(response.text))
        if extracted is not None:
            return extracted

    fallback_request = request.model_copy(
        update={
            "response_schema": None,
            "prompt": f"{request.prompt}\n\n{_PROMPT_ONLY_INSTRUCTION}",
        }
    )
    response = provider.complete(fallback_request)
    recovered = _validated(_extract_json(response.text))
    if recovered is not None:
        return recovered

    raise LLMOutputError(
        f"{provider.name} did not return output matching {model_cls.__name__} "
        f"after {max_retries + 1} attempt(s) and a prompt-only fallback."
    ) from last_error
