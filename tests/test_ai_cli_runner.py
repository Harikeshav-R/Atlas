"""Tests for the subprocess boundary in :mod:`atlas.ai.cli.runner`."""

from __future__ import annotations

import subprocess

import pytest

from atlas.ai.cli import RunResult, SubprocessRunner
from tests.conftest import FakeSubprocessRunner


def test_run_result_holds_streams_separately() -> None:
    result = RunResult(returncode=0, stdout="out", stderr="err")
    assert result.returncode == 0
    assert result.stdout == "out"
    assert result.stderr == "err"


def test_run_result_is_frozen() -> None:
    result = RunResult(returncode=0, stdout="", stderr="")
    with pytest.raises(AttributeError):
        result.returncode = 1  # type: ignore[misc]


def test_fake_runner_conforms_to_protocol() -> None:
    runner = FakeSubprocessRunner(RunResult(returncode=0, stdout="", stderr=""))
    assert isinstance(runner, SubprocessRunner)


def test_fake_runner_returns_scripted_result_and_records_call() -> None:
    runner = FakeSubprocessRunner(RunResult(returncode=0, stdout="hi", stderr=""))
    result = runner(
        ["claude", "--version"],
        cwd="/tmp/scratch",
        input_text="prompt",
        timeout_s=42,
        env={"KEY": "value"},
    )
    assert result.stdout == "hi"
    call = runner.calls[0]
    assert call.argv == ["claude", "--version"]
    assert call.cwd == "/tmp/scratch"
    assert call.input_text == "prompt"
    assert call.timeout_s == 42
    assert call.env == {"KEY": "value"}


def test_fake_runner_raises_when_configured() -> None:
    runner = FakeSubprocessRunner(raises=FileNotFoundError("claude"))
    with pytest.raises(FileNotFoundError):
        runner([], cwd=None, input_text=None, timeout_s=1, env=None)
    # The attempted call is still recorded before raising.
    assert runner.calls[0].argv == []


def test_fake_runner_requires_result_or_raises() -> None:
    runner = FakeSubprocessRunner()
    with pytest.raises(AssertionError, match="needs a result or a raises"):
        runner(["x"], cwd=None, input_text=None, timeout_s=1, env=None)


def test_fake_runner_can_replay_timeout() -> None:
    runner = FakeSubprocessRunner(raises=subprocess.TimeoutExpired(cmd="claude", timeout=1))
    with pytest.raises(subprocess.TimeoutExpired):
        runner(["claude"], cwd=None, input_text=None, timeout_s=1, env=None)
