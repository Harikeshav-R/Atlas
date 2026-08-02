"""End-to-end seam test: the LiteLLM provider feeding :func:`complete_json`.

Proves that a LiteLLM-shaped response flows through the shipping
:class:`~atlas.ai.api.provider.LiteLLMProvider` and then through the
structured-output recovery ladder to a validated Pydantic model, without
importing ``litellm`` or making a network call. Because OpenRouter models expose
schema support inconsistently, this also exercises the *text-recovery* path
(``complete_json`` extracting JSON from the message body) that the provider
relies on when ``response_format`` is omitted.
"""

from __future__ import annotations

from pydantic import BaseModel

from atlas.ai import LLMRequest, complete_json
from atlas.ai.api import LiteLLMProvider, ModelCapabilities
from tests.conftest import FakeChatCompleter, FakeModelResponse


class Extraction(BaseModel):
    """The structured result the caller wants back."""

    functions: list[str]


def _no_schema_support(model: str) -> ModelCapabilities:
    return ModelCapabilities(supports_response_schema=False)


def test_json_in_message_body_flows_through_complete_json() -> None:
    # The model returns JSON wrapped in prose/code fence; brace-balancing recovers it.
    body = 'Here you go:\n```json\n{"functions": ["main", "parse"]}\n```'
    completer = FakeChatCompleter(FakeModelResponse(content=body))
    provider = LiteLLMProvider(
        name="openrouter",
        model="openrouter/anthropic/claude-sonnet",
        api_key="test-key",
        completion=completer,
        capabilities=_no_schema_support,
    )

    result = complete_json(provider, LLMRequest(system=None, prompt="list funcs"), Extraction)

    assert result == Extraction(functions=["main", "parse"])
    # The model lacked schema support, so no response_format was ever requested.
    assert all(call.response_format is None for call in completer.calls)
