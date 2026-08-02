"""Per-model capability lookup for the API provider.

The design requires model capabilities to be *queried per model from a registry,
not hardcoded* (PROJECT.md §5.1a): Atlas requests structured JSON output only from
models that actually support it and degrades gracefully elsewhere. LiteLLM ships
that registry (its bundled model-cost/info map), so :func:`default_capabilities`
consults it — but, like the completion call, behind an injectable
:class:`CapabilityFn` seam so the hermetic test suite never imports ``litellm``
(AGENTS.md §6.2) and can pose a model as supporting (or not) structured output.

Only the one capability that changes request shaping today —
``supports_response_schema`` — is modelled; the object is deliberately
extensible (max tokens, temperature limits, …) as later phases need it.
"""

from __future__ import annotations

from typing import Protocol

from pydantic import BaseModel

__all__ = ["CapabilityFn", "ModelCapabilities", "default_capabilities"]


class ModelCapabilities(BaseModel):
    """What a given model can do, as far as request shaping cares.

    Attributes:
        supports_response_schema: Whether the model accepts a JSON-schema
            ``response_format`` (native structured output). When ``False`` the
            provider omits ``response_format`` and relies on
            :func:`atlas.ai.complete_json.complete_json` to recover structure
            from plain text.
    """

    supports_response_schema: bool = False


class CapabilityFn(Protocol):
    """Callable returning the :class:`ModelCapabilities` for a model id.

    Implementations must not raise for an unknown model — they return
    conservative defaults (no structured-output support) so Atlas simply
    degrades to text recovery rather than failing.
    """

    def __call__(self, model: str) -> ModelCapabilities:
        """Return the capabilities of ``model``."""


def default_capabilities(model: str) -> ModelCapabilities:  # pragma: no cover
    """Look up ``model`` capabilities via LiteLLM's bundled registry.

    ``litellm`` is imported lazily so the heavy import happens only when real
    capabilities are queried, never at module load. An unknown model (or any
    lookup error) yields conservative defaults rather than raising, so an
    unrecognized OpenRouter slug degrades to text-based recovery.

    Pragma'd: consults the real LiteLLM registry, which the hermetic suite never
    touches (AGENTS.md §6.2); tests inject a fake :class:`CapabilityFn`.
    """
    import litellm

    try:
        supports_schema = bool(litellm.supports_response_schema(model=model))
    except Exception:
        supports_schema = False
    return ModelCapabilities(supports_response_schema=supports_schema)
