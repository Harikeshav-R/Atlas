"""Failover chain across AI backends.

:class:`FailoverProvider` wraps an ordered list of :class:`~atlas.ai.base.LLMProvider`
backends and is itself an ``LLMProvider``, so every caller
(:func:`atlas.ai.complete_json.complete_json`, and the matching/tailoring code in
later phases) stays agnostic — a chain is just another provider. On a
backend-availability failure it moves to the next backend in order, per
``docs/PROJECT.md`` §5.1: "on hard error, auth failure, or quota/rate-limit, try
the next backend in the configured chain (e.g. Claude Code → OpenRouter)."

Failover is the **last resort, after** content recovery: an
:class:`~atlas.ai.base.LLMOutputError` (raised by ``complete_json`` once its
JSON-repair ladder is exhausted for a backend) is *not* a failover trigger and
propagates immediately. The triggers are :class:`~atlas.ai.base.LLMBackendError`
(which subsumes :class:`~atlas.ai.base.LLMAuthError` and
:class:`~atlas.ai.base.LLMRateLimitError`) and :class:`~atlas.ai.base.LLMTimeoutError`.

:func:`build_provider_chain` assembles the chain from :class:`~atlas.config.schema.AiConfig`,
mapping ``default_backend`` followed by each ``failover`` name onto the concrete
provider factories.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from atlas.ai.api.openrouter import build_openrouter_provider
from atlas.ai.base import (
    LLMBackendError,
    LLMError,
    LLMProvider,
    LLMRequest,
    LLMResponse,
    LLMTimeoutError,
)
from atlas.ai.cli.claude_code import build_claude_code_provider
from atlas.ai.cli.runner import SubprocessRunner, default_subprocess_runner

if TYPE_CHECKING:
    from collections.abc import Iterator, Sequence

    from atlas.config.schema import AiConfig
    from atlas.config.secrets import SecretStore

__all__ = ["FailoverProvider", "build_named_provider", "build_provider_chain"]

# Errors that mean "this backend is unavailable, try the next one". A tuple so it
# can be used directly in ``except``. ``LLMBackendError`` covers ``LLMAuthError``
# and ``LLMRateLimitError``; ``LLMTimeoutError`` is a sibling under ``LLMError``.
# ``LLMOutputError`` is deliberately excluded — it is a content/schema failure,
# not a backend-availability signal, so it propagates and stops the walk.
_FAILOVER_ERRORS = (LLMBackendError, LLMTimeoutError)


class FailoverProvider:
    """An :class:`~atlas.ai.base.LLMProvider` that tries backends in order.

    Wraps an ordered sequence of providers; each call is attempted against them
    in turn until one succeeds, failing over on backend-availability errors.
    Satisfies the ``LLMProvider`` protocol structurally, so it composes anywhere
    a single provider does.
    """

    def __init__(self, providers: Sequence[LLMProvider]) -> None:
        """Store the ordered backends.

        Args:
            providers: The backends to try, in priority order.

        Raises:
            ValueError: If ``providers`` is empty (a chain with no backends can
                never succeed — caught here rather than at first call).
        """
        if not providers:
            raise ValueError("FailoverProvider requires at least one provider.")
        self._providers: tuple[LLMProvider, ...] = tuple(providers)
        self.name = f"failover({','.join(p.name for p in self._providers)})"

    def is_available(self) -> bool:
        """Return whether *any* wrapped backend reports itself available."""
        return any(provider.is_available() for provider in self._providers)

    def complete(self, request: LLMRequest) -> LLMResponse:
        """Return the first backend's successful response, failing over on error.

        Tries each backend in order. A failover-triggering error
        (:data:`_FAILOVER_ERRORS`) advances to the next backend; any other error
        (e.g. :class:`~atlas.ai.base.LLMOutputError`) propagates immediately. If
        every backend fails over, the last such error is re-raised.
        """
        last_error: LLMError | None = None
        for provider in self._providers:
            try:
                return provider.complete(request)
            except _FAILOVER_ERRORS as exc:
                last_error = exc
        # ``last_error`` is set because the loop ran at least once (non-empty by
        # construction) and only ``_FAILOVER_ERRORS`` reach here.
        assert last_error is not None
        raise last_error

    def stream(self, request: LLMRequest) -> Iterator[str]:
        """Stream from the first backend that starts successfully.

        Uses the same failover rule as :meth:`complete`: a backend that raises a
        failover-triggering error before yielding is skipped; the first stream
        that begins is delegated to fully. If every backend fails over, the last
        such error is re-raised.
        """
        last_error: LLMError | None = None
        for provider in self._providers:
            try:
                # Materialize the first chunk so a backend that fails immediately
                # triggers failover rather than raising mid-iteration to the caller.
                iterator = provider.stream(request)
                first = next(iterator)
            except _FAILOVER_ERRORS as exc:
                last_error = exc
                continue
            return _prepend(first, iterator)
        assert last_error is not None
        raise last_error


def _prepend(first: str, rest: Iterator[str]) -> Iterator[str]:
    """Yield ``first`` then the remaining chunks of ``rest``."""
    yield first
    yield from rest


def build_named_provider(
    name: str,
    config: AiConfig,
    store: SecretStore,
    *,
    runner: SubprocessRunner = default_subprocess_runner,
) -> LLMProvider:
    """Build the single provider identified by ``name`` from ``config``.

    Maps each known backend name to its concrete factory. Used both by
    :func:`build_provider_chain` and by ``atlas doctor`` to construct and inspect
    one backend at a time.

    Args:
        name: The backend name (e.g. ``"claude_code"`` or ``"openrouter"``).
        config: The ``[ai]`` configuration holding per-backend settings.
        store: The secret store passed to the provider factory.
        runner: The subprocess boundary for CLI backends; defaults to the real
            runner and is replaced by a fake in tests.

    Returns:
        The constructed provider.

    Raises:
        LLMError: If ``name`` is not a known backend.
    """
    if name == "claude_code":
        return build_claude_code_provider(config.backends.claude_code, store, runner=runner)
    if name == "openrouter":
        return build_openrouter_provider(config.backends.openrouter, store)
    raise LLMError(f"Unknown AI backend {name!r} in configuration.")


def build_provider_chain(
    config: AiConfig,
    store: SecretStore,
    *,
    runner: SubprocessRunner = default_subprocess_runner,
) -> FailoverProvider:
    """Build the ordered failover chain from ``config``.

    The chain order is ``config.default_backend`` followed by each name in
    ``config.failover`` (e.g. ``claude_code`` → ``openrouter``). Each name is
    mapped to its backend settings and concrete factory.

    Args:
        config: The ``[ai]`` configuration (backend selection + per-backend
            settings).
        store: The secret store passed to each provider factory for key
            resolution.
        runner: The subprocess boundary for CLI backends; defaults to the real
            runner and is replaced by a fake in tests.

    Returns:
        A :class:`FailoverProvider` over the configured backends, in order.

    Raises:
        LLMError: If a configured backend name is not recognized.
    """
    names = [config.default_backend, *config.failover]
    providers = [build_named_provider(name, config, store, runner=runner) for name in names]
    return FailoverProvider(providers)
