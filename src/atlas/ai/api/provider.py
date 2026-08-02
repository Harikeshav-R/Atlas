"""The LiteLLM-backed API provider — Atlas's hosted-model backend.

:class:`LiteLLMProvider` implements :class:`~atlas.ai.base.LLMProvider` for
*every* API backend (OpenRouter, Bedrock, Anthropic, Gemini, DeepSeek, Groq,
Ollama, any OpenAI-compatible endpoint), so adding a vendor is configuration,
not code (PROJECT.md §5.1a). It sits behind two injectable seams — the
:class:`~atlas.ai.api.client.CompletionFn` call boundary and the
:class:`~atlas.ai.api.capabilities.CapabilityFn` registry lookup — so the heavy
``litellm`` import never happens in the hermetic test suite (AGENTS.md §6.2) and
the whole provider is exercised through fakes.

Retry layering (PROJECT.md §5.1a) is respected strictly: *transport* retries
(network/5xx/rate-limit) live in the LiteLLM boundary via ``num_retries``; this
provider never re-retries transport. *Content* retries (bad/truncated JSON) are
the separate concern of :func:`atlas.ai.complete_json.complete_json`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, NoReturn

from atlas.ai.api.capabilities import (
    CapabilityFn,
    default_capabilities,
)
from atlas.ai.api.client import CompletionFn, default_completion
from atlas.ai.base import (
    LLMAuthError,
    LLMBackendError,
    LLMRateLimitError,
    LLMRequest,
    LLMResponse,
    LLMTimeoutError,
    Usage,
)

if TYPE_CHECKING:
    from collections.abc import Iterator

__all__ = ["LiteLLMProvider"]

# HTTP status codes used to classify a failed call without importing LiteLLM's
# exception types. LiteLLM re-exports OpenAI-style errors that carry a
# ``status_code``; matching on the code keeps this module dependency-free and
# robust to LiteLLM's class hierarchy shifting between versions.
_AUTH_STATUS = frozenset({401, 403})
_RATE_LIMIT_STATUS = frozenset({429})

# Case-insensitive substrings identifying a transport timeout, whose exception
# (``litellm.Timeout``) has no HTTP status code to match on.
_TIMEOUT_MARKERS = ("timeout", "timed out")


class LiteLLMProvider:
    """:class:`~atlas.ai.base.LLMProvider` backed by ``litellm.completion``.

    Instances satisfy the provider protocol structurally. Construct one directly
    for a fully custom endpoint, or use :func:`atlas.ai.api.openrouter.build_openrouter_provider`
    for the configured OpenRouter defaults.
    """

    def __init__(
        self,
        *,
        name: str,
        model: str,
        api_key: str | None = None,
        api_base: str | None = None,
        num_retries: int = 2,
        timeout_factor: float = 1.0,
        completion: CompletionFn = default_completion,
        capabilities: CapabilityFn = default_capabilities,
    ) -> None:
        """Configure the provider.

        Args:
            name: The backend identifier, e.g. ``"openrouter"``.
            model: The LiteLLM model id to call (e.g.
                ``"openrouter/anthropic/claude-sonnet"``).
            api_key: The resolved API key, passed to LiteLLM directly and never
                written to :data:`os.environ` (PROJECT.md §5.1a). ``None`` when
                the endpoint needs no key (e.g. a local model).
            api_base: Optional base URL for OpenAI-compatible / local endpoints.
            num_retries: Transport retries handed to LiteLLM (network/5xx/rate
                limit). This is the *transport* retry layer; content retries are
                :func:`atlas.ai.complete_json.complete_json`'s concern.
            timeout_factor: Per-provider multiplier applied to each request's
                ``timeout_s`` to scale the LiteLLM call timeout (a slower vendor
                gets proportionally longer).
            completion: The injected LiteLLM call boundary (fake in tests).
            capabilities: The injected per-model capability lookup (fake in
                tests).
        """
        self.name = name
        self._model = model
        self._api_key = api_key
        self._api_base = api_base
        self._num_retries = num_retries
        self._timeout_factor = timeout_factor
        self._completion = completion
        self._capabilities = capabilities

    def is_available(self) -> bool:
        """Return whether the backend is usable.

        A model id is always configured; the backend is considered available
        when it either needs no key (a local endpoint via ``api_base``) or has
        one. Actual connectivity/auth is proven by ``atlas doctor``'s round-trip
        probe (a later phase), not by this cheap check.
        """
        return self._api_key is not None or self._api_base is not None

    def _messages(self, request: LLMRequest) -> list[dict[str, str]]:
        """Build the chat ``messages`` list from ``request``.

        A system prompt, when present, becomes the leading ``system`` message;
        the task prompt is always the trailing ``user`` message.
        """
        messages: list[dict[str, str]] = []
        if request.system is not None:
            messages.append({"role": "system", "content": request.system})
        messages.append({"role": "user", "content": request.prompt})
        return messages

    def _response_format(self, request: LLMRequest) -> dict[str, Any] | None:
        """Return the LiteLLM ``response_format`` for ``request``, or ``None``.

        Structured output is requested only when the caller supplied a schema
        *and* the model reports it supports one (capabilities from the registry,
        not hardcoded). Otherwise ``None`` is returned and
        :func:`atlas.ai.complete_json.complete_json` recovers structure from
        text.
        """
        if request.response_schema is None:
            return None
        if not self._capabilities(self._model).supports_response_schema:
            return None
        return {
            "type": "json_schema",
            "json_schema": {"name": "response", "schema": request.response_schema},
        }

    def _timeout_for(self, request: LLMRequest) -> int:
        """Scale ``request.timeout_s`` by the per-provider factor (min 1s)."""
        return max(1, int(request.timeout_s * self._timeout_factor))

    def complete(self, request: LLMRequest) -> LLMResponse:
        """Run ``request`` through LiteLLM and return the parsed response.

        Raises:
            LLMAuthError: On an authentication/authorization failure (401/403).
            LLMRateLimitError: On a rate-limit or quota failure (429).
            LLMTimeoutError: On a transport timeout.
            LLMBackendError: On any other failure, or an unusable response.
        """
        try:
            raw = self._completion(
                model=self._model,
                messages=self._messages(request),
                api_key=self._api_key,
                api_base=self._api_base,
                timeout_s=self._timeout_for(request),
                temperature=request.temperature,
                max_tokens=request.max_tokens,
                response_format=self._response_format(request),
                num_retries=self._num_retries,
            )
        except Exception as exc:
            self._classify_error(exc)
        return self._parse_response(raw)

    def stream(self, request: LLMRequest) -> Iterator[str]:
        """Yield the completed response text as a single chunk.

        Token-level streaming is deferred; this satisfies the
        :class:`~atlas.ai.base.LLMProvider` protocol.
        """
        yield self.complete(request).text

    def _classify_error(self, exc: Exception) -> NoReturn:
        """Raise the mapped Atlas error for a LiteLLM ``exc``.

        Classifies by HTTP ``status_code`` where present (auth vs. rate limit)
        and by message for the status-less timeout, defaulting to a generic
        :class:`~atlas.ai.base.LLMBackendError`. Messages stay generic so vendor
        diagnostics, URLs, and secrets never surface to the user; the original
        exception is chained for daemon-side logging.
        """
        status = getattr(exc, "status_code", None)
        if status in _AUTH_STATUS:
            raise LLMAuthError(f"{self.name} authentication failed.") from exc
        if status in _RATE_LIMIT_STATUS:
            raise LLMRateLimitError(f"{self.name} was rate-limited or over quota.") from exc
        if any(marker in str(exc).lower() for marker in _TIMEOUT_MARKERS):
            raise LLMTimeoutError(f"{self.name} timed out.") from exc
        raise LLMBackendError(f"{self.name} call failed.") from exc

    def _parse_response(self, raw: Any) -> LLMResponse:
        """Map LiteLLM's ``ModelResponse`` onto an :class:`LLMResponse`.

        Reads the first choice's message content, token usage, and (when
        LiteLLM computed it) the per-call cost from ``_hidden_params``. Access is
        defensive ``getattr``/``dict`` traversal so this module never imports
        LiteLLM's types.

        Raises:
            LLMBackendError: If the response carries no usable choice/content.
        """
        text = self._extract_text(raw)
        return LLMResponse(
            text=text,
            structured=None,
            raw=self._raw_dict(raw),
            usage=self._extract_usage(raw),
            model=getattr(raw, "model", None) or self._model,
            backend=self.name,
        )

    def _extract_text(self, raw: Any) -> str:
        """Return the assistant text from the first choice, or raise.

        Raises:
            LLMBackendError: If choices are missing/empty or the content is not
                a string (a malformed or empty completion).
        """
        choices = getattr(raw, "choices", None)
        if not choices:
            raise LLMBackendError(f"{self.name} returned no choices.")
        content = getattr(getattr(choices[0], "message", None), "content", None)
        if not isinstance(content, str):
            raise LLMBackendError(f"{self.name} returned an empty response.")
        return content

    def _extract_usage(self, raw: Any) -> Usage:
        """Build :class:`Usage` from the response's token counts and cost."""
        usage = getattr(raw, "usage", None)
        hidden = getattr(raw, "_hidden_params", None)
        cost = hidden.get("response_cost") if isinstance(hidden, dict) else None
        return Usage(
            input_tokens=getattr(usage, "prompt_tokens", None),
            output_tokens=getattr(usage, "completion_tokens", None),
            total_tokens=getattr(usage, "total_tokens", None),
            cost_usd=cost,
        )

    def _raw_dict(self, raw: Any) -> dict[str, Any] | None:
        """Return the response as a plain dict for debugging, or ``None``.

        Uses ``model_dump()`` when available (LiteLLM's ``ModelResponse`` is a
        Pydantic model); anything else is left out of ``raw`` rather than risk a
        non-serializable object.
        """
        dump = getattr(raw, "model_dump", None)
        if callable(dump):
            result: dict[str, Any] = dump()
            return result
        return None
