"""Tests for the CLI adapter base class in :mod:`atlas.ai.cli.base`."""

from __future__ import annotations

import subprocess
from collections.abc import Mapping
from typing import NoReturn

import pytest

from atlas.ai import (
    LLMAuthError,
    LLMBackendError,
    LLMProvider,
    LLMRequest,
    LLMResponse,
    LLMTimeoutError,
    Usage,
)
from atlas.ai.cli import CliAdapter, RunResult, parse_cli_version
from tests.conftest import FakeSubprocessRunner


class _StubAdapter(CliAdapter):
    """Minimal concrete adapter that exercises the base class mechanics."""

    name = "stub"

    def _build_argv(self, request: LLMRequest) -> list[str]:
        return [self._command, "-p", request.prompt]

    def _parse_response(self, result: RunResult, request: LLMRequest) -> LLMResponse:
        # Mirror the real adapters: prefer a native structured field, always
        # populate text, and stash the raw stdout for debugging.
        structured = {"echo": result.stdout} if result.stdout else None
        return LLMResponse(
            text=result.stdout,
            structured=structured,
            raw={"stdout": result.stdout, "stderr": result.stderr},
            usage=Usage(cost_usd=0.0),
            model="stub-model",
            backend=self.name,
        )


class _HookAdapter(_StubAdapter):
    """Stub that overrides the env and error-classification hooks."""

    name = "hook"

    def _env_for(self, request: LLMRequest) -> Mapping[str, str] | None:
        return {"INJECTED": "1"}

    def _classify_error(self, result: RunResult) -> NoReturn:
        raise LLMAuthError(f"{self.name} auth failed.")


def _request() -> LLMRequest:
    return LLMRequest(system=None, prompt="hello")


def test_adapter_conforms_to_llm_provider() -> None:
    adapter = _StubAdapter(command="stub", runner=FakeSubprocessRunner())
    assert isinstance(adapter, LLMProvider)


def test_is_available_true_on_zero_exit() -> None:
    runner = FakeSubprocessRunner(RunResult(returncode=0, stdout="v1", stderr=""))
    adapter = _StubAdapter(command="stub", runner=runner)
    assert adapter.is_available() is True
    # The version probe ran the configured command with --version.
    assert runner.calls[0].argv == ["stub", "--version"]


def test_is_available_false_on_nonzero_exit() -> None:
    runner = FakeSubprocessRunner(RunResult(returncode=1, stdout="", stderr="boom"))
    adapter = _StubAdapter(command="stub", runner=runner)
    assert adapter.is_available() is False


def test_is_available_false_when_binary_missing() -> None:
    runner = FakeSubprocessRunner(raises=FileNotFoundError("stub"))
    adapter = _StubAdapter(command="stub", runner=runner)
    assert adapter.is_available() is False


def test_complete_happy_path_populates_response() -> None:
    runner = FakeSubprocessRunner(RunResult(returncode=0, stdout="answer", stderr=""))
    adapter = _StubAdapter(command="stub", runner=runner)
    response = adapter.complete(_request())
    assert response.text == "answer"
    assert response.structured == {"echo": "answer"}
    assert response.model == "stub-model"
    assert response.backend == "stub"
    assert response.usage is not None


def test_complete_runs_in_scratch_directory() -> None:
    runner = FakeSubprocessRunner(RunResult(returncode=0, stdout="ok", stderr=""))
    adapter = _StubAdapter(command="stub", runner=runner)
    adapter.complete(_request())
    # A throwaway working directory is passed so project files aren't picked up.
    assert runner.calls[0].cwd is not None
    assert "atlas-cli-" in runner.calls[0].cwd


def test_complete_raises_backend_error_on_nonzero_exit() -> None:
    runner = FakeSubprocessRunner(RunResult(returncode=2, stdout="", stderr="secret path /x"))
    adapter = _StubAdapter(command="stub", runner=runner)
    with pytest.raises(LLMBackendError, match="exited with code 2") as excinfo:
        adapter.complete(_request())
    # The generic message must not leak stderr diagnostics.
    assert "secret path" not in str(excinfo.value)


def test_complete_raises_timeout_error() -> None:
    runner = FakeSubprocessRunner(raises=subprocess.TimeoutExpired(cmd="stub", timeout=120))
    adapter = _StubAdapter(command="stub", runner=runner)
    with pytest.raises(LLMTimeoutError, match="timed out after 120s") as excinfo:
        adapter.complete(_request())
    assert isinstance(excinfo.value.__cause__, subprocess.TimeoutExpired)


def test_parse_response_yields_none_structured_for_empty_stdout() -> None:
    runner = FakeSubprocessRunner(RunResult(returncode=0, stdout="", stderr=""))
    adapter = _StubAdapter(command="stub", runner=runner)
    response = adapter.complete(_request())
    assert response.structured is None
    assert response.text == ""


def test_stream_yields_single_completed_chunk() -> None:
    runner = FakeSubprocessRunner(RunResult(returncode=0, stdout="streamed", stderr=""))
    adapter = _StubAdapter(command="stub", runner=runner)
    assert list(adapter.stream(_request())) == ["streamed"]


def test_complete_forwards_request_timeout() -> None:
    runner = FakeSubprocessRunner(RunResult(returncode=0, stdout="ok", stderr=""))
    adapter = _StubAdapter(command="stub", runner=runner)
    adapter.complete(LLMRequest(system=None, prompt="p", timeout_s=7))
    assert runner.calls[0].timeout_s == 7


def test_env_hook_defaults_to_none() -> None:
    runner = FakeSubprocessRunner(RunResult(returncode=0, stdout="ok", stderr=""))
    adapter = _StubAdapter(command="stub", runner=runner)
    adapter.complete(_request())
    assert runner.calls[0].env is None


def test_env_hook_override_is_threaded_to_runner() -> None:
    runner = FakeSubprocessRunner(RunResult(returncode=0, stdout="ok", stderr=""))
    adapter = _HookAdapter(command="hook", runner=runner)
    adapter.complete(_request())
    assert runner.calls[0].env == {"INJECTED": "1"}


def test_classify_error_override_is_honored() -> None:
    runner = FakeSubprocessRunner(RunResult(returncode=1, stdout="", stderr="nope"))
    adapter = _HookAdapter(command="hook", runner=runner)
    with pytest.raises(LLMAuthError, match="auth failed"):
        adapter.complete(_request())


# --- version parsing + floor ----------------------------------------------------


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("2.1.220 (Claude Code)", (2, 1, 220)),
        ("v3.0.1", (3, 0, 1)),
        ("  1.2.3  ", (1, 2, 3)),
        ("not a version", None),
        ("1.2", None),
        ("", None),
    ],
)
def test_parse_cli_version(text: str, expected: tuple[int, int, int] | None) -> None:
    assert parse_cli_version(text) == expected


class _FlooredAdapter(_StubAdapter):
    """Stub adapter that requires a minimum version."""

    name = "floored"

    def _minimum_version(self) -> tuple[int, int, int]:
        return (2, 1, 205)


def test_check_availability_reason_when_binary_missing() -> None:
    runner = FakeSubprocessRunner(raises=FileNotFoundError("stub"))
    result = _FlooredAdapter(command="stub", runner=runner).check_availability()
    assert result.available is False
    assert "not found" in result.reason


def test_check_availability_reason_on_nonzero_exit() -> None:
    runner = FakeSubprocessRunner(RunResult(returncode=1, stdout="", stderr="boom"))
    result = _FlooredAdapter(command="stub", runner=runner).check_availability()
    assert result.available is False
    assert "probe failed" in result.reason


def test_is_available_false_below_version_floor() -> None:
    runner = FakeSubprocessRunner(RunResult(returncode=0, stdout="2.1.100 (stub)", stderr=""))
    adapter = _FlooredAdapter(command="stub", runner=runner)
    result = adapter.check_availability()
    assert result.available is False
    assert "too old" in result.reason
    assert ">= 2.1.205" in result.reason


def test_is_available_true_at_or_above_floor() -> None:
    runner = FakeSubprocessRunner(RunResult(returncode=0, stdout="2.1.205 (stub)", stderr=""))
    assert _FlooredAdapter(command="stub", runner=runner).is_available() is True


def test_is_available_true_when_version_unparseable() -> None:
    # An unrecognized --version format on a zero exit is not punished.
    runner = FakeSubprocessRunner(RunResult(returncode=0, stdout="mystery build", stderr=""))
    assert _FlooredAdapter(command="stub", runner=runner).is_available() is True
