"""Tests for the AI provider contract in :mod:`atlas.ai.base`."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from atlas.ai import (
    LLMError,
    LLMOutputError,
    LLMProvider,
    LLMRequest,
    LLMResponse,
    Usage,
)
from tests.conftest import FakeLLMProvider, FakeProviderFactory, make_response


def test_usage_defaults_to_all_none() -> None:
    usage = Usage()
    assert usage.input_tokens is None
    assert usage.output_tokens is None
    assert usage.total_tokens is None
    assert usage.cost_usd is None


def test_usage_records_reported_values() -> None:
    usage = Usage(input_tokens=10, output_tokens=5, total_tokens=15, cost_usd=0.02)
    assert usage.total_tokens == 15
    assert usage.cost_usd == pytest.approx(0.02)


def test_llm_request_defaults() -> None:
    request = LLMRequest(system=None, prompt="hi")
    assert request.response_schema is None
    assert request.max_tokens is None
    assert request.temperature is None
    assert request.timeout_s == 120


def test_llm_request_requires_prompt() -> None:
    with pytest.raises(ValidationError):
        LLMRequest(system="s")  # type: ignore[call-arg]


def test_llm_response_defaults() -> None:
    response = LLMResponse(text="hello", model="m", backend="b")
    assert response.structured is None
    assert response.raw is None
    assert response.usage is None


def test_llm_response_carries_structured_and_usage() -> None:
    response = LLMResponse(
        text="{}",
        structured={"ok": True},
        raw={"native": 1},
        usage=Usage(total_tokens=3),
        model="m",
        backend="b",
    )
    assert response.structured == {"ok": True}
    assert response.raw == {"native": 1}
    assert response.usage is not None
    assert response.usage.total_tokens == 3


def test_error_hierarchy() -> None:
    assert issubclass(LLMOutputError, LLMError)
    assert issubclass(LLMError, Exception)


def test_fake_provider_conforms_to_protocol() -> None:
    provider = FakeLLMProvider([make_response(text="ok")])
    assert isinstance(provider, LLMProvider)


def test_fake_provider_completes_and_records_calls() -> None:
    provider = FakeLLMProvider([make_response(text="answer")])
    request = LLMRequest(system=None, prompt="q")
    response = provider.complete(request)
    assert response.text == "answer"
    assert provider.calls == [request]


def test_fake_provider_availability_flag() -> None:
    assert FakeLLMProvider([], available=False).is_available() is False
    assert FakeLLMProvider([], available=True).is_available() is True


def test_fake_provider_supports_callable_script() -> None:
    provider = FakeLLMProvider([lambda req: make_response(text=req.prompt.upper())])
    assert provider.complete(LLMRequest(system=None, prompt="hi")).text == "HI"


def test_fake_provider_streams_full_text() -> None:
    provider = FakeLLMProvider([make_response(text="chunked")])
    assert list(provider.stream(LLMRequest(system=None, prompt="q"))) == ["chunked"]


def test_fake_provider_raises_when_script_exhausted() -> None:
    provider = FakeLLMProvider([])
    with pytest.raises(AssertionError, match="script exhausted"):
        provider.complete(LLMRequest(system=None, prompt="q"))


def test_make_fake_provider_fixture(make_fake_provider: FakeProviderFactory) -> None:
    # The fixture returns a factory; exercise its keyword arguments.
    provider = make_fake_provider([make_response(text="x")], name="custom", available=False)
    assert provider.name == "custom"
    assert provider.is_available() is False
    assert provider.complete(LLMRequest(system=None, prompt="q")).text == "x"
