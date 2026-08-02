"""Tests for the LiteLLM API provider in :mod:`atlas.ai.api.provider`."""

from __future__ import annotations

import pytest

from atlas.ai import (
    LLMAuthError,
    LLMBackendError,
    LLMProvider,
    LLMRateLimitError,
    LLMRequest,
    LLMTimeoutError,
)
from atlas.ai.api import LiteLLMProvider, ModelCapabilities
from tests.conftest import (
    FakeChatCompleter,
    FakeChoice,
    FakeLiteLLMError,
    FakeMessage,
    FakeModelResponse,
    FakeUsage,
)


def _caps(*, supports: bool = False) -> object:
    """Return a capability lookup reporting a fixed schema-support answer."""

    def lookup(model: str) -> ModelCapabilities:
        return ModelCapabilities(supports_response_schema=supports)

    return lookup


def _provider(
    completer: FakeChatCompleter,
    *,
    supports_schema: bool = False,
    **kwargs: object,
) -> LiteLLMProvider:
    params: dict[str, object] = {
        "name": "openrouter",
        "model": "openrouter/anthropic/claude-sonnet",
        "api_key": "test-key",
        "completion": completer,
        "capabilities": _caps(supports=supports_schema),
    }
    params.update(kwargs)
    return LiteLLMProvider(**params)  # type: ignore[arg-type]


def _request(**kwargs: object) -> LLMRequest:
    params: dict[str, object] = {"system": None, "prompt": "hi"}
    params.update(kwargs)
    return LLMRequest(**params)  # type: ignore[arg-type]


def test_provider_conforms_to_llm_provider() -> None:
    assert isinstance(_provider(FakeChatCompleter(FakeModelResponse())), LLMProvider)


# --- is_available ---------------------------------------------------------------


def test_is_available_true_with_api_key() -> None:
    provider = _provider(FakeChatCompleter(FakeModelResponse()))
    assert provider.is_available() is True


def test_is_available_true_with_api_base_and_no_key() -> None:
    provider = _provider(
        FakeChatCompleter(FakeModelResponse()),
        api_key=None,
        api_base="http://localhost:11434",
    )
    assert provider.is_available() is True


def test_is_available_false_without_key_or_base() -> None:
    provider = _provider(FakeChatCompleter(FakeModelResponse()), api_key=None, api_base=None)
    assert provider.is_available() is False


# --- request shaping ------------------------------------------------------------


def test_messages_user_only_without_system() -> None:
    completer = FakeChatCompleter(FakeModelResponse())
    _provider(completer).complete(_request(prompt="do it"))
    assert completer.calls[0].messages == [{"role": "user", "content": "do it"}]


def test_messages_prepend_system_when_present() -> None:
    completer = FakeChatCompleter(FakeModelResponse())
    _provider(completer).complete(_request(system="be terse", prompt="do it"))
    assert completer.calls[0].messages == [
        {"role": "system", "content": "be terse"},
        {"role": "user", "content": "do it"},
    ]


def test_call_forwards_key_temperature_max_tokens_and_retries() -> None:
    completer = FakeChatCompleter(FakeModelResponse())
    _provider(completer, num_retries=5).complete(_request(temperature=0.4, max_tokens=256))
    call = completer.calls[0]
    assert call.api_key == "test-key"
    assert call.temperature == pytest.approx(0.4)
    assert call.max_tokens == 256
    assert call.num_retries == 5
    assert call.model == "openrouter/anthropic/claude-sonnet"


def test_response_format_omitted_when_no_schema() -> None:
    completer = FakeChatCompleter(FakeModelResponse())
    _provider(completer, supports_schema=True).complete(_request())
    assert completer.calls[0].response_format is None


def test_response_format_omitted_when_model_lacks_support() -> None:
    completer = FakeChatCompleter(FakeModelResponse())
    schema = {"type": "object", "properties": {"x": {"type": "integer"}}}
    _provider(completer, supports_schema=False).complete(_request(response_schema=schema))
    assert completer.calls[0].response_format is None


def test_response_format_set_when_schema_and_support() -> None:
    completer = FakeChatCompleter(FakeModelResponse())
    schema = {"type": "object", "properties": {"x": {"type": "integer"}}}
    _provider(completer, supports_schema=True).complete(_request(response_schema=schema))
    fmt = completer.calls[0].response_format
    assert fmt == {
        "type": "json_schema",
        "json_schema": {"name": "response", "schema": schema},
    }


# --- adaptive timeout -----------------------------------------------------------


def test_timeout_scaled_by_factor() -> None:
    completer = FakeChatCompleter(FakeModelResponse())
    _provider(completer, timeout_factor=2.0).complete(_request(timeout_s=120))
    assert completer.calls[0].timeout_s == 240


def test_timeout_never_below_one_second() -> None:
    completer = FakeChatCompleter(FakeModelResponse())
    _provider(completer, timeout_factor=0.0).complete(_request(timeout_s=120))
    assert completer.calls[0].timeout_s == 1


# --- response mapping -----------------------------------------------------------


def test_complete_maps_text_usage_cost_and_model() -> None:
    response_obj = FakeModelResponse(
        content="the answer",
        model="openrouter/anthropic/claude-sonnet",
        usage=FakeUsage(prompt_tokens=11, completion_tokens=4, total_tokens=15),
        response_cost=0.0009,
    )
    provider = _provider(FakeChatCompleter(response_obj))
    response = provider.complete(_request())
    assert response.text == "the answer"
    assert response.structured is None
    assert response.model == "openrouter/anthropic/claude-sonnet"
    assert response.backend == "openrouter"
    assert response.usage is not None
    assert response.usage.input_tokens == 11
    assert response.usage.output_tokens == 4
    assert response.usage.total_tokens == 15
    assert response.usage.cost_usd == pytest.approx(0.0009)
    assert response.raw is not None
    assert response.raw["model"] == "openrouter/anthropic/claude-sonnet"


def test_complete_model_falls_back_to_configured_when_absent() -> None:
    provider = _provider(FakeChatCompleter(FakeModelResponse(model=None)))
    assert provider.complete(_request()).model == "openrouter/anthropic/claude-sonnet"


def test_usage_all_none_when_response_has_no_usage() -> None:
    provider = _provider(FakeChatCompleter(FakeModelResponse(usage=None, response_cost=None)))
    usage = provider.complete(_request()).usage
    assert usage is not None
    assert usage.input_tokens is None
    assert usage.total_tokens is None
    assert usage.cost_usd is None


def test_raw_is_none_when_response_not_dumpable() -> None:
    provider = _provider(FakeChatCompleter(FakeModelResponse(dumpable=False)))
    assert provider.complete(_request()).raw is None


# --- malformed responses --------------------------------------------------------


def test_complete_raises_when_no_choices() -> None:
    provider = _provider(FakeChatCompleter(FakeModelResponse(choices=[])))
    with pytest.raises(LLMBackendError, match="no choices"):
        provider.complete(_request())


def test_complete_raises_when_content_missing() -> None:
    response_obj = FakeModelResponse(choices=[FakeChoice(FakeMessage(None))])
    provider = _provider(FakeChatCompleter(response_obj))
    with pytest.raises(LLMBackendError, match="empty response"):
        provider.complete(_request())


# --- error classification -------------------------------------------------------


@pytest.mark.parametrize("status", [401, 403])
def test_classify_auth_error(status: int) -> None:
    err = FakeLiteLLMError("Unauthorized at /home/x", status_code=status)
    provider = _provider(FakeChatCompleter(raises=err))
    with pytest.raises(LLMAuthError, match="authentication failed") as excinfo:
        provider.complete(_request())
    # Vendor diagnostics (incl. the path) must not leak into the user message.
    assert "/home/x" not in str(excinfo.value)


def test_classify_rate_limit_error() -> None:
    provider = _provider(FakeChatCompleter(raises=FakeLiteLLMError("slow down", status_code=429)))
    with pytest.raises(LLMRateLimitError, match="rate-limited or over quota"):
        provider.complete(_request())


def test_classify_timeout_error_without_status() -> None:
    provider = _provider(FakeChatCompleter(raises=FakeLiteLLMError("Request timed out")))
    with pytest.raises(LLMTimeoutError, match="timed out"):
        provider.complete(_request())


def test_classify_generic_backend_error() -> None:
    provider = _provider(FakeChatCompleter(raises=FakeLiteLLMError("boom", status_code=500)))
    with pytest.raises(LLMBackendError, match="call failed") as excinfo:
        provider.complete(_request())
    assert type(excinfo.value) is LLMBackendError


# --- streaming ------------------------------------------------------------------


def test_stream_yields_single_chunk() -> None:
    provider = _provider(FakeChatCompleter(FakeModelResponse(content="streamed")))
    assert list(provider.stream(_request())) == ["streamed"]
