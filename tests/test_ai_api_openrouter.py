"""Tests for the OpenRouter factory in :mod:`atlas.ai.api.openrouter`."""

from __future__ import annotations

import pytest

from atlas.ai import LLMRequest
from atlas.ai.api import ModelCapabilities
from atlas.ai.api.openrouter import (
    OPENROUTER_API_KEY_ENV,
    build_openrouter_provider,
)
from atlas.config import OpenRouterBackend, SecretStore
from tests.conftest import FakeChatCompleter, FakeKeyring, FakeModelResponse


def _caps_lookup(model: str) -> ModelCapabilities:
    return ModelCapabilities(supports_response_schema=False)


def _store(fake_keyring: FakeKeyring) -> SecretStore:
    return SecretStore(fake_keyring)


def test_resolves_key_from_keyring_and_prefixes_model(fake_keyring: FakeKeyring) -> None:
    store = _store(fake_keyring)
    store.set("openrouter", "kr-value")
    completer = FakeChatCompleter(FakeModelResponse())

    provider = build_openrouter_provider(
        OpenRouterBackend(model="anthropic/claude-sonnet"),
        store,
        completion=completer,
        capabilities=_caps_lookup,
    )

    provider.complete(LLMRequest(system=None, prompt="hi"))
    call = completer.calls[0]
    assert call.api_key == "kr-value"
    assert call.model == "openrouter/anthropic/claude-sonnet"
    assert provider.name == "openrouter"


def test_already_prefixed_model_is_not_double_prefixed(fake_keyring: FakeKeyring) -> None:
    store = _store(fake_keyring)
    store.set("openrouter", "kr-value")
    completer = FakeChatCompleter(FakeModelResponse())

    provider = build_openrouter_provider(
        OpenRouterBackend(model="openrouter/openai/gpt-4o"),
        store,
        completion=completer,
        capabilities=_caps_lookup,
    )

    provider.complete(LLMRequest(system=None, prompt="hi"))
    assert completer.calls[0].model == "openrouter/openai/gpt-4o"


def test_custom_key_handle_is_used(fake_keyring: FakeKeyring) -> None:
    store = _store(fake_keyring)
    store.set("my-handle", "handle-value")
    completer = FakeChatCompleter(FakeModelResponse())

    provider = build_openrouter_provider(
        OpenRouterBackend(api_key_handle="my-handle"),
        store,
        completion=completer,
        capabilities=_caps_lookup,
    )

    provider.complete(LLMRequest(system=None, prompt="hi"))
    assert completer.calls[0].api_key == "handle-value"


def test_falls_back_to_env_var_when_keyring_empty(
    fake_keyring: FakeKeyring,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(OPENROUTER_API_KEY_ENV, "env-value")
    completer = FakeChatCompleter(FakeModelResponse())

    provider = build_openrouter_provider(
        OpenRouterBackend(),
        _store(fake_keyring),
        completion=completer,
        capabilities=_caps_lookup,
    )

    provider.complete(LLMRequest(system=None, prompt="hi"))
    assert completer.calls[0].api_key == "env-value"


def test_api_key_none_when_neither_keyring_nor_env(
    fake_keyring: FakeKeyring,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(OPENROUTER_API_KEY_ENV, raising=False)
    completer = FakeChatCompleter(FakeModelResponse())

    provider = build_openrouter_provider(
        OpenRouterBackend(),
        _store(fake_keyring),
        completion=completer,
        capabilities=_caps_lookup,
    )

    provider.complete(LLMRequest(system=None, prompt="hi"))
    assert completer.calls[0].api_key is None
    # Without a key (or api_base) the backend reports itself unavailable.
    assert provider.is_available() is False
