"""Tests for the Claude Code adapter in :mod:`atlas.ai.cli.claude_code`."""

from __future__ import annotations

import json

import pytest

from atlas.ai import (
    LLMAuthError,
    LLMBackendError,
    LLMProvider,
    LLMRateLimitError,
    LLMRequest,
)
from atlas.ai.cli import (
    ANTHROPIC_API_KEY_ENV,
    ClaudeCodeAdapter,
    RunResult,
    build_claude_code_provider,
)
from atlas.config import ClaudeCodeBackend, SecretStore
from tests.conftest import FakeKeyring, FakeSubprocessRunner


def _adapter(runner: FakeSubprocessRunner, **kwargs: object) -> ClaudeCodeAdapter:
    return ClaudeCodeAdapter(command="claude", runner=runner, **kwargs)  # type: ignore[arg-type]


def _ok_envelope(**extra: object) -> str:
    envelope: dict[str, object] = {
        "result": "the answer",
        "structured_output": {"functions": ["main"]},
        "session_id": "sess-1",
        "usage": {"input_tokens": 12, "output_tokens": 3, "total_tokens": 15},
        "total_cost_usd": 0.004,
        "model": "claude-sonnet",
    }
    envelope.update(extra)
    return json.dumps(envelope)


def _request(**kwargs: object) -> LLMRequest:
    params: dict[str, object] = {"system": None, "prompt": "hi"}
    params.update(kwargs)
    return LLMRequest(**params)  # type: ignore[arg-type]


def test_adapter_conforms_to_llm_provider() -> None:
    assert isinstance(_adapter(FakeSubprocessRunner()), LLMProvider)


def test_build_argv_includes_output_format_and_no_allowed_tools() -> None:
    runner = FakeSubprocessRunner(RunResult(returncode=0, stdout=_ok_envelope(), stderr=""))
    _adapter(runner).complete(_request())
    argv = runner.calls[0].argv
    assert argv[:5] == ["claude", "-p", "hi", "--output-format", "json"]
    assert "--allowedTools" not in argv
    assert "--bare" not in argv


def test_build_argv_omits_schema_when_absent() -> None:
    runner = FakeSubprocessRunner(RunResult(returncode=0, stdout=_ok_envelope(), stderr=""))
    _adapter(runner).complete(_request())
    assert "--json-schema" not in runner.calls[0].argv


def test_build_argv_includes_schema_as_json_string() -> None:
    runner = FakeSubprocessRunner(RunResult(returncode=0, stdout=_ok_envelope(), stderr=""))
    schema = {"type": "object", "properties": {"x": {"type": "integer"}}}
    _adapter(runner).complete(_request(response_schema=schema))
    argv = runner.calls[0].argv
    index = argv.index("--json-schema")
    assert json.loads(argv[index + 1]) == schema


def test_build_argv_appends_system_prompt_with_neutralize_instruction() -> None:
    runner = FakeSubprocessRunner(RunResult(returncode=0, stdout=_ok_envelope(), stderr=""))
    _adapter(runner).complete(_request(system="You are helpful."))
    argv = runner.calls[0].argv
    index = argv.index("--append-system-prompt")
    injected = argv[index + 1]
    assert injected.startswith("You are helpful.")
    assert "do not use any tools" in injected


def test_build_argv_neutralize_instruction_without_caller_system() -> None:
    runner = FakeSubprocessRunner(RunResult(returncode=0, stdout=_ok_envelope(), stderr=""))
    _adapter(runner).complete(_request())
    argv = runner.calls[0].argv
    index = argv.index("--append-system-prompt")
    assert "do not use any tools" in argv[index + 1]


def test_build_argv_includes_model_when_set() -> None:
    runner = FakeSubprocessRunner(RunResult(returncode=0, stdout=_ok_envelope(), stderr=""))
    _adapter(runner, model="claude-opus").complete(_request())
    argv = runner.calls[0].argv
    index = argv.index("--model")
    assert argv[index + 1] == "claude-opus"


def test_non_bare_mode_inherits_environment() -> None:
    runner = FakeSubprocessRunner(RunResult(returncode=0, stdout=_ok_envelope(), stderr=""))
    _adapter(runner).complete(_request())
    assert runner.calls[0].env is None


def test_bare_mode_injects_api_key_into_merged_env() -> None:
    runner = FakeSubprocessRunner(RunResult(returncode=0, stdout=_ok_envelope(), stderr=""))
    _adapter(runner, use_bare=True, api_key="secret-key").complete(_request())
    argv = runner.calls[0].argv
    env = runner.calls[0].env
    assert "--bare" in argv
    assert env is not None
    assert env["ANTHROPIC_API_KEY"] == "secret-key"
    # Merged onto the inherited environment (PATH is present on all CI OSes).
    assert "PATH" in env


def test_bare_mode_without_key_raises_auth_error() -> None:
    with pytest.raises(LLMAuthError, match="requires an API key"):
        _adapter(FakeSubprocessRunner(), use_bare=True)


def test_complete_maps_envelope_fields() -> None:
    runner = FakeSubprocessRunner(RunResult(returncode=0, stdout=_ok_envelope(), stderr=""))
    response = _adapter(runner).complete(_request())
    assert response.text == "the answer"
    assert response.structured == {"functions": ["main"]}
    assert response.model == "claude-sonnet"
    assert response.backend == "claude_code"
    assert response.usage is not None
    assert response.usage.input_tokens == 12
    assert response.usage.output_tokens == 3
    assert response.usage.total_tokens == 15
    assert response.usage.cost_usd == pytest.approx(0.004)
    # The session id has no LLMResponse field but survives in raw for resume.
    assert response.raw is not None
    assert response.raw["session_id"] == "sess-1"


def test_complete_structured_none_when_absent() -> None:
    stdout = json.dumps({"result": "text only"})
    runner = FakeSubprocessRunner(RunResult(returncode=0, stdout=stdout, stderr=""))
    response = _adapter(runner).complete(_request())
    assert response.structured is None
    assert response.text == "text only"


def test_complete_missing_usage_yields_all_none_tokens() -> None:
    stdout = json.dumps({"result": "x"})
    runner = FakeSubprocessRunner(RunResult(returncode=0, stdout=stdout, stderr=""))
    response = _adapter(runner).complete(_request())
    assert response.usage is not None
    assert response.usage.input_tokens is None
    assert response.usage.cost_usd is None


def test_complete_model_falls_back_to_configured_then_name() -> None:
    stdout = json.dumps({"result": "x"})
    runner = FakeSubprocessRunner(RunResult(returncode=0, stdout=stdout, stderr=""))
    # No model in envelope, configured model present -> configured wins.
    response = _adapter(runner, model="claude-opus").complete(_request())
    assert response.model == "claude-opus"


def test_complete_model_falls_back_to_backend_name() -> None:
    stdout = json.dumps({"result": "x"})
    runner = FakeSubprocessRunner(RunResult(returncode=0, stdout=stdout, stderr=""))
    # No model in envelope, no configured model -> backend name.
    response = _adapter(runner).complete(_request())
    assert response.model == "claude_code"


def test_complete_raises_backend_error_on_unparseable_stdout() -> None:
    runner = FakeSubprocessRunner(RunResult(returncode=0, stdout="not json", stderr=""))
    with pytest.raises(LLMBackendError, match="unparseable output"):
        _adapter(runner).complete(_request())


def test_classify_auth_failure() -> None:
    runner = FakeSubprocessRunner(
        RunResult(returncode=1, stdout="", stderr="Error: Unauthorized (401) — check /home/x")
    )
    with pytest.raises(LLMAuthError, match="authentication failed") as excinfo:
        _adapter(runner).complete(_request())
    # Diagnostics (incl. the path) must not leak into the user-facing message.
    assert "/home/x" not in str(excinfo.value)


def test_classify_rate_limit_failure() -> None:
    runner = FakeSubprocessRunner(
        RunResult(returncode=1, stdout="", stderr="Error: rate limit exceeded (429)")
    )
    with pytest.raises(LLMRateLimitError, match="rate-limited or over quota"):
        _adapter(runner).complete(_request())


def test_classify_generic_backend_failure() -> None:
    runner = FakeSubprocessRunner(RunResult(returncode=3, stdout="", stderr="some other failure"))
    with pytest.raises(LLMBackendError, match="exited with code 3") as excinfo:
        _adapter(runner).complete(_request())
    assert type(excinfo.value) is LLMBackendError


# --- build_claude_code_provider -------------------------------------------------


def _store(fake_keyring: FakeKeyring) -> SecretStore:
    return SecretStore(fake_keyring)


def test_factory_non_bare_builds_adapter_without_key(fake_keyring: FakeKeyring) -> None:
    # Even with a key present in the store, non-bare mode must not resolve it.
    store = _store(fake_keyring)
    store.set("anthropic", "should-not-be-used")
    runner = FakeSubprocessRunner(RunResult(returncode=0, stdout=_ok_envelope(), stderr=""))

    provider = build_claude_code_provider(
        ClaudeCodeBackend(command="claude", use_bare=False),
        store,
        runner=runner,
    )

    assert isinstance(provider, ClaudeCodeAdapter)
    provider.complete(_request())
    # Non-bare inherits the environment; no --bare and no injected key.
    assert runner.calls[0].env is None
    assert "--bare" not in runner.calls[0].argv


def test_factory_bare_resolves_key_from_keyring(fake_keyring: FakeKeyring) -> None:
    store = _store(fake_keyring)
    store.set("anthropic", "kr-secret")
    runner = FakeSubprocessRunner(RunResult(returncode=0, stdout=_ok_envelope(), stderr=""))

    provider = build_claude_code_provider(
        ClaudeCodeBackend(use_bare=True),
        store,
        runner=runner,
    )
    provider.complete(_request())

    env = runner.calls[0].env
    assert "--bare" in runner.calls[0].argv
    assert env is not None
    assert env["ANTHROPIC_API_KEY"] == "kr-secret"


def test_factory_bare_custom_handle(fake_keyring: FakeKeyring) -> None:
    store = _store(fake_keyring)
    store.set("my-anthropic", "handle-secret")
    runner = FakeSubprocessRunner(RunResult(returncode=0, stdout=_ok_envelope(), stderr=""))

    provider = build_claude_code_provider(
        ClaudeCodeBackend(use_bare=True, api_key_handle="my-anthropic"),
        store,
        runner=runner,
    )
    provider.complete(_request())

    env = runner.calls[0].env
    assert env is not None
    assert env["ANTHROPIC_API_KEY"] == "handle-secret"


def test_factory_bare_falls_back_to_env_var(
    fake_keyring: FakeKeyring,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(ANTHROPIC_API_KEY_ENV, "env-secret")
    runner = FakeSubprocessRunner(RunResult(returncode=0, stdout=_ok_envelope(), stderr=""))

    provider = build_claude_code_provider(
        ClaudeCodeBackend(use_bare=True),
        _store(fake_keyring),
        runner=runner,
    )
    provider.complete(_request())

    env = runner.calls[0].env
    assert env is not None
    assert env["ANTHROPIC_API_KEY"] == "env-secret"


def test_factory_bare_without_key_raises_auth_error(
    fake_keyring: FakeKeyring,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(ANTHROPIC_API_KEY_ENV, raising=False)
    with pytest.raises(LLMAuthError, match="requires an API key"):
        build_claude_code_provider(ClaudeCodeBackend(use_bare=True), _store(fake_keyring))
