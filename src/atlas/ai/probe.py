"""Live capability probe for AI backends.

PROJECT.md §5.1 calls for a capability probe that runs "a tiny 'reply OK as JSON
against this schema' round-trip" against each backend and records support for
**JSON output, JSON schema, streaming, system-prompt injection, and model
override**, so Atlas can drive per-backend behavior and pick the best output
mode. :func:`probe_backend` is that probe.

It is **pure logic over the** :class:`~atlas.ai.base.LLMProvider` **protocol** — it
takes an already-constructed provider, issues a couple of tiny calls, and reads
the responses. It never builds providers or touches config/keyring, so the
default test suite drives it with a fake provider and no live call ever happens
outside the ``atlas doctor --probe`` opt-in (AGENTS.md §6.2).

Confidence differs by capability: ``json_output`` and ``json_schema`` are read
deterministically from the response; ``system_prompt``, ``streaming`` and
``model_override`` are **best-effort** signals (model compliance and transport
vary), documented as such on :class:`BackendCapabilities`.

Cost: at most three live calls per probe — one primary ``complete``, one
``stream`` (streaming check), and one extra ``complete`` only when an
``override_provider`` (a second provider built with a different model) is
supplied to test model-override support.

Names here are intentionally distinct from the API layer's static-registry
:class:`~atlas.ai.api.capabilities.ModelCapabilities` / ``CapabilityFn``, which
is a per-model LiteLLM lookup consulted at request-shaping time — a different
concern from this live per-backend probe.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel

from atlas.ai.base import LLMError, LLMRequest

if TYPE_CHECKING:
    from atlas.ai.base import LLMProvider, LLMResponse

__all__ = ["PROBE_SCHEMA", "BackendCapabilities", "ProbeResult", "probe_backend"]

# The sentinel the probe asks the backend to echo, to test system-prompt honoring.
_SENTINEL = "atlas-probe-ok"

# A minimal JSON Schema the round-trip must satisfy. Kept tiny to minimize cost.
PROBE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {"ok": {"type": "boolean"}, "echo": {"type": "string"}},
    "required": ["ok"],
}

# The task prompt and the system instruction that requests the sentinel echo.
_PROBE_PROMPT = (
    'Reply with a JSON object {"ok": true, "echo": "<the exact value of ECHO given '
    'in the system instruction>"}. Do not include any other text.'
)
_PROBE_SYSTEM = f'You are a probe. ECHO = "{_SENTINEL}". Follow the user instruction exactly.'


class BackendCapabilities(BaseModel):
    """What a backend supports, as observed by a live probe round-trip.

    Attributes:
        json_output: The backend returned parseable JSON at all (deterministic:
            a native structured object, or text that parses as JSON).
        json_schema: The backend honored the requested JSON Schema, i.e. it
            populated its native structured field with a schema-conforming object
            (deterministic, the strongest signal).
        streaming: ``stream()`` yielded at least one chunk without erroring
            (best-effort).
        system_prompt: The backend honored a system instruction, detected by
            echoing a sentinel back (best-effort — depends on model compliance).
        model_override: A call against a provider built with an overridden model
            id succeeded (best-effort; ``False`` when no override was probed).
    """

    json_output: bool = False
    json_schema: bool = False
    streaming: bool = False
    system_prompt: bool = False
    model_override: bool = False


class ProbeResult(BaseModel):
    """The outcome of probing one backend.

    Attributes:
        backend: The probed backend's name.
        ok: Whether the primary round-trip succeeded at all.
        capabilities: The observed capabilities (all ``False`` when ``ok`` is
            ``False``).
        detail: A short, generic human-readable summary (no secrets or paths).
        error: A generic failure reason when ``ok`` is ``False``; ``None``
            otherwise.
    """

    backend: str
    ok: bool
    capabilities: BackendCapabilities
    detail: str
    error: str | None = None


def _parses_as_json_object(text: str) -> bool:
    """Return whether ``text`` parses as a JSON object."""
    try:
        return isinstance(json.loads(text), dict)
    except (json.JSONDecodeError, ValueError):
        return False


def _read_json_capabilities(response: LLMResponse) -> tuple[bool, bool]:
    """Return ``(json_output, json_schema)`` read from ``response``.

    ``json_schema`` is true only when the native structured field holds a dict
    with the schema's required ``ok`` key (the strongest signal a schema was
    honored). ``json_output`` is true for that, or for any text that parses as a
    JSON object.
    """
    structured = response.structured
    if isinstance(structured, dict):
        return True, "ok" in structured
    return _parses_as_json_object(response.text), False


def _honored_system_prompt(response: LLMResponse) -> bool:
    """Return whether the sentinel came back (system instruction honored)."""
    structured = response.structured
    if isinstance(structured, dict) and structured.get("echo") == _SENTINEL:
        return True
    return _SENTINEL in response.text


def _probe_streaming(provider: LLMProvider, request: LLMRequest) -> bool:
    """Return whether ``provider.stream`` yields at least one chunk.

    Best-effort: any error (including an :class:`~atlas.ai.base.LLMError` from a
    backend that does not really stream) is treated as "no streaming" rather
    than failing the whole probe.
    """
    try:
        for _ in provider.stream(request):
            return True
    except LLMError:
        return False
    return False


def _probe_model_override(override_provider: LLMProvider, request: LLMRequest) -> bool:
    """Return whether a call to ``override_provider`` succeeds (best-effort).

    ``override_provider`` is a second provider built with a different model id
    (model selection is a construction-time property of a provider, not a field
    of :class:`~atlas.ai.base.LLMRequest`), so a successful call demonstrates the
    backend accepts the override.
    """
    try:
        override_provider.complete(request)
    except LLMError:
        return False
    return True


def probe_backend(
    provider: LLMProvider,
    *,
    override_provider: LLMProvider | None = None,
) -> ProbeResult:
    """Probe ``provider`` with a tiny round-trip and report its capabilities.

    Issues one primary ``complete`` with :data:`PROBE_SCHEMA` and a sentinel
    system prompt, then a ``stream`` check, and — only when ``override_provider``
    is given — one more ``complete`` against it. Reads JSON output/schema
    deterministically and system-prompt/streaming/model-override best-effort.

    Any :class:`~atlas.ai.base.LLMError` from the primary call yields
    ``ok=False`` with a generic reason (secrets, paths, and vendor diagnostics
    are never surfaced).

    Args:
        provider: An already-constructed backend to probe.
        override_provider: An optional second provider built with a different
            model id, used to test model-override support; when ``None`` the
            model-override capability is left ``False``.

    Returns:
        The :class:`ProbeResult` for ``provider``.
    """
    request = LLMRequest(system=_PROBE_SYSTEM, prompt=_PROBE_PROMPT, response_schema=PROBE_SCHEMA)
    try:
        response = provider.complete(request)
    except LLMError as exc:
        return ProbeResult(
            backend=provider.name,
            ok=False,
            capabilities=BackendCapabilities(),
            detail="probe failed",
            error=str(exc),
        )

    json_output, json_schema = _read_json_capabilities(response)
    capabilities = BackendCapabilities(
        json_output=json_output,
        json_schema=json_schema,
        system_prompt=_honored_system_prompt(response),
        streaming=_probe_streaming(provider, request),
        model_override=(
            _probe_model_override(override_provider, request)
            if override_provider is not None
            else False
        ),
    )
    return ProbeResult(
        backend=provider.name,
        ok=True,
        capabilities=capabilities,
        detail="probe succeeded",
    )
