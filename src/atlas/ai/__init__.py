"""Atlas AI provider abstraction.

A single :class:`~atlas.ai.base.LLMProvider` interface fronts every AI backend
(coding-CLI subprocess adapters and the LiteLLM API provider), and
:func:`~atlas.ai.complete_json.complete_json` gives all of them a shared,
provider-agnostic path to validated structured output. See ``docs/PROJECT.md``
§5.1 and ``docs/agent/llm-integration.md``.

This package currently ships the core contract (models, protocol, error
hierarchy) and the ``complete_json`` recovery ladder. Concrete backends, the
failover router, capability probing, and caching arrive in later phases.
"""

from __future__ import annotations

from atlas.ai.base import (
    LLMAuthError,
    LLMBackendError,
    LLMError,
    LLMOutputError,
    LLMProvider,
    LLMRateLimitError,
    LLMRequest,
    LLMResponse,
    LLMTimeoutError,
    Usage,
)
from atlas.ai.complete_json import complete_json

__all__ = [
    "LLMAuthError",
    "LLMBackendError",
    "LLMError",
    "LLMOutputError",
    "LLMProvider",
    "LLMRateLimitError",
    "LLMRequest",
    "LLMResponse",
    "LLMTimeoutError",
    "Usage",
    "complete_json",
]
