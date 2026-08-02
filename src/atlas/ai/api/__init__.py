"""LiteLLM-backed API adapters for the Atlas AI layer.

A single :class:`~atlas.ai.api.provider.LiteLLMProvider` implements
:class:`~atlas.ai.base.LLMProvider` for every hosted model provider (OpenRouter,
Bedrock, Anthropic, Gemini, DeepSeek, Groq, Ollama, OpenAI-compatible), so adding
a vendor is configuration rather than code (PROJECT.md §5.1a). LiteLLM is kept
behind two injectable seams — the :class:`~atlas.ai.api.client.CompletionFn` call
boundary and the :class:`~atlas.ai.api.capabilities.CapabilityFn` registry lookup
— so its heavy import never happens in the hermetic test suite (AGENTS.md §6.2)
and the API path stays swappable.

This package ships the provider, both seams, and the
:func:`~atlas.ai.api.openrouter.build_openrouter_provider` factory for Atlas's
default API failover backend. Additional vendor factories and a cached
``litellm.Router`` arrive in later phases.
"""

from __future__ import annotations

from atlas.ai.api.capabilities import (
    CapabilityFn,
    ModelCapabilities,
    default_capabilities,
)
from atlas.ai.api.client import CompletionFn, default_completion
from atlas.ai.api.openrouter import (
    OPENROUTER_API_KEY_ENV,
    build_openrouter_provider,
)
from atlas.ai.api.provider import LiteLLMProvider

__all__ = [
    "OPENROUTER_API_KEY_ENV",
    "CapabilityFn",
    "CompletionFn",
    "LiteLLMProvider",
    "ModelCapabilities",
    "build_openrouter_provider",
    "default_capabilities",
    "default_completion",
]
