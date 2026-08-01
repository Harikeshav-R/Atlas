"""Core contract for Atlas's AI provider abstraction.

This module defines the single interface every AI backend implements and the
request/response value objects that flow across it, plus the normalized error
hierarchy callers can catch regardless of which backend produced the failure.

The design is specified in ``docs/PROJECT.md`` §5.1. Concrete backends — the
coding-CLI subprocess adapters (``atlas.ai.cli``) and the LiteLLM API provider
(``atlas.ai.api``) — are introduced in later phases; this module intentionally
depends on nothing beyond Pydantic so it can be the shared foundation they build
on.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel

# ``dict[str, Any]`` is used for backend-native payloads and JSON Schemas below.
# The ``Any`` is deliberate: these carry arbitrary JSON whose shape Atlas does not
# and should not constrain at this layer (see docs/agent/coding-standards.md).

__all__ = [
    "LLMBackendError",
    "LLMError",
    "LLMOutputError",
    "LLMProvider",
    "LLMRequest",
    "LLMResponse",
    "LLMTimeoutError",
    "Usage",
]


class Usage(BaseModel):
    """Token and cost accounting for a single AI call.

    Every field is optional because backends report usage inconsistently: a
    coding CLI may return a dollar cost with no token counts, an API backend may
    return tokens with no cost, and a local model may report neither. Atlas
    records whatever the backend provides into the ``ai_call`` table.
    """

    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    cost_usd: float | None = None


class LLMRequest(BaseModel):
    """A single request to an AI backend.

    Atlas asks for JSON when it needs structure by setting ``response_schema`` to
    a JSON Schema (typically derived from a Pydantic model); providers enforce or
    validate it. Fields mirror the contract in ``docs/PROJECT.md`` §5.1.

    Attributes:
        system: System prompt / instructions, or ``None`` for backend defaults.
        prompt: The user-facing task prompt.
        response_schema: JSON Schema the response must conform to, if structured
            output is required; ``None`` for free-text responses.
        max_tokens: Optional cap on generated tokens.
        temperature: Optional sampling temperature.
        timeout_s: Per-call timeout in seconds.
    """

    system: str | None
    prompt: str
    response_schema: dict[str, Any] | None = None
    max_tokens: int | None = None
    temperature: float | None = None
    timeout_s: int = 120


class LLMResponse(BaseModel):
    """A single response from an AI backend.

    Attributes:
        text: The backend's free-text answer (its ``result``/``response`` field).
        structured: The backend's parsed structured object when it natively
            returned one (a CLI ``structured_output`` field or an API JSON-mode
            object), normalized to a plain dict; ``None`` otherwise. This is the
            happy-path source :func:`atlas.ai.complete_json.complete_json` reads.
        raw: The un-normalized backend-native payload, kept for debugging.
        usage: Token/cost accounting when the backend reports it.
        model: The model identifier the backend used.
        backend: The provider name that produced this response.
    """

    text: str
    structured: dict[str, Any] | None = None
    raw: dict[str, Any] | None = None
    usage: Usage | None = None
    model: str
    backend: str


@runtime_checkable
class LLMProvider(Protocol):
    """The interface every AI backend implements.

    A provider is any object exposing a ``name`` and the three methods below.
    The protocol is ``runtime_checkable`` so tests and capability probing can
    assert conformance with ``isinstance``.
    """

    name: str

    def is_available(self) -> bool:
        """Return whether this backend is usable (binary present, auth in place)."""

    def complete(self, request: LLMRequest) -> LLMResponse:
        """Run ``request`` to completion and return the backend's response."""

    def stream(self, request: LLMRequest) -> Iterator[str]:
        """Run ``request`` and yield response text incrementally as it arrives."""


class LLMError(Exception):
    """Base class for every error raised by the Atlas AI provider layer."""


class LLMOutputError(LLMError):
    """Raised when a backend's output cannot be coerced into the requested schema.

    :func:`atlas.ai.complete_json.complete_json` raises this after its full
    recovery ladder — native structured field, brace-balanced extraction,
    bounded content retries, and a prompt-only fallback — has been exhausted.
    """


class LLMTimeoutError(LLMError):
    """Raised when a backend call exceeds its timeout.

    For CLI backends the child process tree is terminated before this is raised
    (see :mod:`atlas.ai.cli`).
    """


class LLMBackendError(LLMError):
    """Raised when a backend fails to produce a usable response.

    Covers a non-zero process exit and an unparseable or malformed response
    envelope. User-facing messages stay generic; details are logged rather than
    surfaced so paths and diagnostics do not leak.
    """
