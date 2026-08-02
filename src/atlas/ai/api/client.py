"""The LiteLLM call boundary for the API provider.

API backends (:mod:`atlas.ai.api`) reach every hosted model through
`LiteLLM <https://github.com/BerriAI/litellm>`_. To keep that dependency behind
an injectable seam — and the default test suite hermetic and fast (importing
``litellm`` alone costs seconds and pulls a large dependency tree, so it must
never load in unit tests, per AGENTS.md §6.2) — the provider depends on the
:class:`CompletionFn` protocol rather than importing ``litellm`` directly.
Production wiring uses :func:`default_completion`, which lazily imports and calls
``litellm.completion``; tests inject a fake that records its keyword arguments
and replays canned responses (or raises).

Keeping ``litellm`` behind this seam also preserves the swappability the design
calls for (PROJECT.md §5.1a): the default implementation can later grow into a
cached ``litellm.Router`` + ``RetryPolicy`` without the provider changing, since
transport retries (network/5xx/rate-limit) belong here, not in callers.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from collections.abc import Sequence

__all__ = ["CompletionFn", "default_completion"]

# The completion object returned across this seam is LiteLLM's ``ModelResponse``,
# duck-typed as ``Any`` so this module (and the provider) need not import
# ``litellm`` to be type-checked. :func:`atlas.ai.api.provider` reads it through
# defensive ``getattr`` access. This ``Any`` is the deliberate, documented seam
# boundary (see the module docstring), not an escape hatch.


class CompletionFn(Protocol):
    """Callable that runs one chat completion and returns LiteLLM's response.

    The single implementation Atlas ships is :func:`default_completion`; tests
    inject a fake. Implementations must raise on failure (LiteLLM's own
    exception types in production); the provider normalizes those into the
    shared :mod:`atlas.ai.base` error hierarchy.
    """

    def __call__(
        self,
        *,
        model: str,
        messages: Sequence[dict[str, str]],
        api_key: str | None,
        api_base: str | None,
        timeout_s: int,
        temperature: float | None,
        max_tokens: int | None,
        response_format: dict[str, Any] | None,
        num_retries: int,
    ) -> Any:
        """Run the completion for ``model`` and return the raw response object."""


def default_completion(  # pragma: no cover
    *,
    model: str,
    messages: Sequence[dict[str, str]],
    api_key: str | None,
    api_base: str | None,
    timeout_s: int,
    temperature: float | None,
    max_tokens: int | None,
    response_format: dict[str, Any] | None,
    num_retries: int,
) -> Any:
    """Call ``litellm.completion`` and return its ``ModelResponse``.

    ``litellm`` is imported lazily here so the (heavy) import happens only when a
    real API call is made, never at module load. ``num_retries`` gives LiteLLM
    the transport-retry layer the design assigns to it (PROJECT.md §5.1a), and
    ``drop_params=True`` lets LiteLLM silently drop request parameters a given
    model does not support (e.g. ``response_format`` on models without structured
    output) rather than erroring — the :func:`atlas.ai.complete_json.complete_json`
    ladder then recovers structure from plain text.

    This thin boundary carries ``# pragma: no cover`` because the default test
    suite never performs a real API call or imports ``litellm`` (AGENTS.md §6.2);
    the provider is exercised through an injected fake completer instead.
    """
    import litellm

    return litellm.completion(
        model=model,
        messages=list(messages),
        api_key=api_key,
        api_base=api_base,
        timeout=timeout_s,
        temperature=temperature,
        max_tokens=max_tokens,
        response_format=response_format,
        num_retries=num_retries,
        drop_params=True,
    )
