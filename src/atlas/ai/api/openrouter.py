"""OpenRouter provider factory — Atlas's default API failover backend.

OpenRouter is the API backend Atlas fails over to when the default coding CLI is
unavailable (PROJECT.md §10, §18.1). This module wires the OpenRouter
configuration (:class:`~atlas.config.schema.OpenRouterBackend`) and the resolved
keyring secret onto a :class:`~atlas.ai.api.provider.LiteLLMProvider`, so callers
get a ready provider without touching LiteLLM specifics.

The API key is resolved once here via :func:`~atlas.config.secrets.resolve_api_key`
(keyring first) and passed to the provider directly — never written to
:data:`os.environ` (PROJECT.md §5.1a). The env-var fallback stays enabled
(``OPENROUTER_API_KEY``) because OpenRouter is a hosted, non-local provider; only
local providers disable it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from atlas.ai.api.capabilities import CapabilityFn, default_capabilities
from atlas.ai.api.client import CompletionFn, default_completion
from atlas.ai.api.provider import LiteLLMProvider
from atlas.config.secrets import resolve_api_key

if TYPE_CHECKING:
    from atlas.config.schema import OpenRouterBackend
    from atlas.config.secrets import SecretStore

__all__ = ["OPENROUTER_API_KEY_ENV", "build_openrouter_provider"]

#: Backend identifier (matches the ``[ai.backends.openrouter]`` config key).
_BACKEND_NAME = "openrouter"

#: Prefix LiteLLM uses to route a model id to OpenRouter.
_MODEL_PREFIX = "openrouter/"

#: Environment variable consulted as a fallback when the keyring has no key.
OPENROUTER_API_KEY_ENV = "OPENROUTER_API_KEY"


def _qualified_model(model: str) -> str:
    """Return ``model`` with the ``openrouter/`` routing prefix LiteLLM expects.

    Config stores the vendor slug (e.g. ``anthropic/claude-sonnet``); LiteLLM
    routes it to OpenRouter only when prefixed. An already-prefixed value is
    returned unchanged so a fully-qualified config value still works.
    """
    if model.startswith(_MODEL_PREFIX):
        return model
    return f"{_MODEL_PREFIX}{model}"


def build_openrouter_provider(
    config: OpenRouterBackend,
    store: SecretStore,
    *,
    completion: CompletionFn = default_completion,
    capabilities: CapabilityFn = default_capabilities,
) -> LiteLLMProvider:
    """Build a :class:`LiteLLMProvider` for OpenRouter from config + keyring.

    Resolves the API key from ``store`` under the configured handle (falling
    back to ``OPENROUTER_API_KEY``) and returns a provider targeting the
    configured, ``openrouter/``-prefixed model. The ``completion`` and
    ``capabilities`` seams default to the real lazy-import boundaries and are
    injected only by tests (referencing the defaults does not import
    ``litellm`` — that happens lazily inside them).

    Args:
        config: The ``[ai.backends.openrouter]`` settings (model + key handle).
        store: The secret store to resolve the API key from.
        completion: The LiteLLM call boundary (fake in tests).
        capabilities: The per-model capability lookup (fake in tests).

    Returns:
        A configured provider ready to :meth:`~atlas.ai.api.provider.LiteLLMProvider.complete`.
    """
    api_key = resolve_api_key(
        store,
        config.api_key_handle,
        env_var=OPENROUTER_API_KEY_ENV,
        allow_env_fallback=True,
    )
    return LiteLLMProvider(
        name=_BACKEND_NAME,
        model=_qualified_model(config.model),
        api_key=api_key,
        completion=completion,
        capabilities=capabilities,
    )
