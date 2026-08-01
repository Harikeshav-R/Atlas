"""Atlas AI provider abstraction.

A single :class:`~atlas.ai.base.LLMProvider` interface fronts every AI backend
(coding-CLI subprocess adapters and the LiteLLM API provider). See
``docs/PROJECT.md`` §5.1 and ``docs/agent/llm-integration.md``.

This package currently ships the core contract (models, protocol, error
hierarchy). The shared structured-output helper, concrete backends, the failover
router, capability probing, and caching arrive in later phases.
"""

from __future__ import annotations

from atlas.ai.base import (
    LLMError,
    LLMOutputError,
    LLMProvider,
    LLMRequest,
    LLMResponse,
    Usage,
)

__all__ = [
    "LLMError",
    "LLMOutputError",
    "LLMProvider",
    "LLMRequest",
    "LLMResponse",
    "Usage",
]
