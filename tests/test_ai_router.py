"""Tests for the failover chain in :mod:`atlas.ai.router`."""

from __future__ import annotations

import pytest

from atlas.ai import (
    LLMAuthError,
    LLMBackendError,
    LLMError,
    LLMOutputError,
    LLMProvider,
    LLMRateLimitError,
    LLMRequest,
    LLMResponse,
    LLMTimeoutError,
)
from atlas.ai.api import LiteLLMProvider
from atlas.ai.cli import ClaudeCodeAdapter
from atlas.ai.router import FailoverProvider, build_provider_chain
from atlas.config import AiConfig, SecretStore
from tests.conftest import (
    FakeKeyring,
    FakeLLMProvider,
    FakeSubprocessRunner,
    ScriptedResponse,
    make_response,
)


def _request() -> LLMRequest:
    return LLMRequest(system=None, prompt="hi")


def _raiser(exc: BaseException) -> ScriptedResponse:
    """A scripted entry that raises ``exc`` when the provider is called."""

    def _fail(request: LLMRequest) -> LLMResponse:
        raise exc

    return _fail


# --- construction ---------------------------------------------------------------


def test_empty_chain_rejected() -> None:
    with pytest.raises(ValueError, match="at least one provider"):
        FailoverProvider([])


def test_conforms_to_llm_provider() -> None:
    provider = FailoverProvider([FakeLLMProvider([make_response(text="ok")], name="a")])
    assert isinstance(provider, LLMProvider)


def test_name_is_composite() -> None:
    chain = FailoverProvider(
        [
            FakeLLMProvider([make_response()], name="claude_code"),
            FakeLLMProvider([make_response()], name="openrouter"),
        ]
    )
    assert chain.name == "failover(claude_code,openrouter)"


# --- is_available ---------------------------------------------------------------


def test_is_available_true_if_any_available() -> None:
    chain = FailoverProvider(
        [
            FakeLLMProvider([make_response()], name="a", available=False),
            FakeLLMProvider([make_response()], name="b", available=True),
        ]
    )
    assert chain.is_available() is True


def test_is_available_false_if_none_available() -> None:
    chain = FailoverProvider(
        [
            FakeLLMProvider([make_response()], name="a", available=False),
            FakeLLMProvider([make_response()], name="b", available=False),
        ]
    )
    assert chain.is_available() is False


# --- complete: success / failover -----------------------------------------------


def test_first_success_skips_rest() -> None:
    first = FakeLLMProvider([make_response(text="from-first")], name="first")
    second = FakeLLMProvider([make_response(text="from-second")], name="second")
    chain = FailoverProvider([first, second])

    response = chain.complete(_request())

    assert response.text == "from-first"
    assert len(first.calls) == 1
    # The second backend is never touched when the first succeeds.
    assert second.calls == []


@pytest.mark.parametrize(
    "error",
    [
        LLMBackendError("hard error"),
        LLMAuthError("auth"),
        LLMRateLimitError("quota"),
        LLMTimeoutError("timeout"),
    ],
)
def test_failover_on_trigger_errors(error: LLMError) -> None:
    first = FakeLLMProvider([_raiser(error)], name="first")
    second = FakeLLMProvider([make_response(text="recovered")], name="second")
    chain = FailoverProvider([first, second])

    response = chain.complete(_request())

    assert response.text == "recovered"
    assert len(first.calls) == 1
    assert len(second.calls) == 1


def test_all_fail_reraises_last_error() -> None:
    first_error = LLMBackendError("first down")
    last_error = LLMRateLimitError("second over quota")
    first = FakeLLMProvider([_raiser(first_error)], name="first")
    second = FakeLLMProvider([_raiser(last_error)], name="second")
    chain = FailoverProvider([first, second])

    with pytest.raises(LLMRateLimitError) as excinfo:
        chain.complete(_request())
    # The LAST backend's error is the one surfaced.
    assert excinfo.value is last_error


def test_output_error_propagates_without_failover() -> None:
    # An LLMOutputError is a content failure, not a backend-availability signal:
    # it must stop the walk immediately, never reaching the second backend.
    first = FakeLLMProvider([_raiser(LLMOutputError("bad json"))], name="first")
    second = FakeLLMProvider([make_response(text="unreached")], name="second")
    chain = FailoverProvider([first, second])

    with pytest.raises(LLMOutputError):
        chain.complete(_request())
    assert second.calls == []


def test_single_provider_error_propagates() -> None:
    only = FakeLLMProvider([_raiser(LLMBackendError("down"))], name="only")
    with pytest.raises(LLMBackendError, match="down"):
        FailoverProvider([only]).complete(_request())


# --- stream ---------------------------------------------------------------------


def test_stream_uses_first_working_backend() -> None:
    first = FakeLLMProvider([make_response(text="streamed-first")], name="first")
    second = FakeLLMProvider([make_response(text="streamed-second")], name="second")
    chain = FailoverProvider([first, second])

    assert list(chain.stream(_request())) == ["streamed-first"]
    assert second.calls == []


def test_stream_fails_over_to_next_backend() -> None:
    first = FakeLLMProvider([_raiser(LLMBackendError("down"))], name="first")
    second = FakeLLMProvider([make_response(text="streamed-second")], name="second")
    chain = FailoverProvider([first, second])

    assert list(chain.stream(_request())) == ["streamed-second"]


def test_stream_all_fail_reraises_last_error() -> None:
    last_error = LLMTimeoutError("second timed out")
    first = FakeLLMProvider([_raiser(LLMBackendError("first down"))], name="first")
    second = FakeLLMProvider([_raiser(last_error)], name="second")
    chain = FailoverProvider([first, second])

    with pytest.raises(LLMTimeoutError) as excinfo:
        list(chain.stream(_request()))
    assert excinfo.value is last_error


# --- build_provider_chain -------------------------------------------------------


def _store() -> SecretStore:
    return SecretStore(FakeKeyring())


def test_build_chain_default_order() -> None:
    chain = build_provider_chain(
        AiConfig(),
        _store(),
        runner=FakeSubprocessRunner(),
    )
    # Default config: default_backend claude_code, failover [openrouter].
    assert chain.name == "failover(claude_code,openrouter)"
    assert isinstance(chain._providers[0], ClaudeCodeAdapter)
    assert isinstance(chain._providers[1], LiteLLMProvider)


def test_build_chain_respects_custom_order() -> None:
    config = AiConfig.model_validate({"default_backend": "openrouter", "failover": ["claude_code"]})
    chain = build_provider_chain(config, _store(), runner=FakeSubprocessRunner())
    assert isinstance(chain._providers[0], LiteLLMProvider)
    assert isinstance(chain._providers[1], ClaudeCodeAdapter)


def test_build_chain_single_backend_no_failover() -> None:
    config = AiConfig.model_validate({"default_backend": "claude_code", "failover": []})
    chain = build_provider_chain(config, _store(), runner=FakeSubprocessRunner())
    assert chain.name == "failover(claude_code)"


def test_build_chain_unknown_backend_raises() -> None:
    config = AiConfig.model_validate({"default_backend": "nope", "failover": []})
    with pytest.raises(LLMError, match="Unknown AI backend 'nope'"):
        build_provider_chain(config, _store(), runner=FakeSubprocessRunner())
