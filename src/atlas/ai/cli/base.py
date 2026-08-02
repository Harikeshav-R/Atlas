"""Shared base class for coding-CLI subprocess adapters.

:class:`CliAdapter` implements the cross-cutting mechanics every coding-CLI
backend needs — running the binary through the injected
:class:`~atlas.ai.cli.runner.SubprocessRunner` in a throwaway scratch directory,
enforcing the per-call timeout, and normalizing failures into the shared
:mod:`atlas.ai.base` error hierarchy — leaving each concrete backend
(:class:`~atlas.ai.base.LLMProvider`) to supply only its own argv, stdin
strategy, and envelope parsing. See ``docs/PROJECT.md`` §5.1 ("CLI adapter
design").
"""

from __future__ import annotations

import subprocess
import tempfile
from abc import ABC, abstractmethod
from collections.abc import Iterator, Mapping, Sequence
from typing import NoReturn

from atlas.ai.base import LLMBackendError, LLMRequest, LLMResponse, LLMTimeoutError
from atlas.ai.cli.runner import RunResult, SubprocessRunner

__all__ = ["CliAdapter"]


class CliAdapter(ABC):
    """Base class for backends that drive a coding CLI headlessly.

    Subclasses set :attr:`name` and implement :meth:`_build_argv` and
    :meth:`_parse_response`; everything else (scratch cwd, timeout handling,
    non-zero-exit detection, error normalization) is provided here. Instances
    satisfy the :class:`~atlas.ai.base.LLMProvider` protocol structurally.
    """

    #: The backend identifier, e.g. ``"claude_code"``. Set by each subclass.
    name: str

    def __init__(self, *, command: str, runner: SubprocessRunner) -> None:
        """Store the CLI binary and the injected subprocess runner.

        Args:
            command: The CLI executable to invoke (name on ``PATH`` or a path).
            runner: The subprocess boundary used for every child process, so the
                adapter never touches :mod:`subprocess` directly (testability).
        """
        self._command = command
        self._runner = runner

    def _version_argv(self) -> list[str]:
        """Return the arguments that make the CLI print its version and exit.

        Overridable; defaults to ``["--version"]``.
        """
        return ["--version"]

    def _stdin_for(self, request: LLMRequest) -> str | None:
        """Return text to pipe to the child via stdin, or ``None`` to use argv.

        Defaults to ``None`` (the prompt travels in the argv built by
        :meth:`_build_argv`); subclasses override when large input should be
        piped instead.
        """
        return None

    def _env_for(self, request: LLMRequest) -> Mapping[str, str] | None:
        """Return the environment for the child process, or ``None`` to inherit.

        Defaults to ``None`` (the child inherits the parent environment);
        subclasses override to inject secrets such as an API key. A returned
        mapping *replaces* the child's whole environment, so an override that
        only adds a variable should merge it onto a copy of the inherited env.
        """
        return None

    def _classify_error(self, result: RunResult) -> NoReturn:
        """Raise the appropriate error for a non-zero-exit ``result``.

        Called by :meth:`complete` when the CLI exits non-zero. The default
        raises a generic :class:`~atlas.ai.base.LLMBackendError`; subclasses
        override to distinguish auth/rate-limit failures. Messages stay generic
        so stderr, paths, and secrets are never surfaced to the user.
        """
        raise LLMBackendError(f"{self.name} exited with code {result.returncode}.")

    def _run(
        self,
        argv: Sequence[str],
        *,
        stdin: str | None,
        timeout_s: int,
        env: Mapping[str, str] | None = None,
    ) -> RunResult:
        """Run ``argv`` in a fresh scratch directory with a timeout.

        The child runs in a throwaway working directory so it never picks up the
        current project's ``CLAUDE.md``, rules, or hooks.

        Raises:
            LLMTimeoutError: If the runner reports the call timed out.
        """
        with tempfile.TemporaryDirectory(prefix="atlas-cli-") as scratch:
            try:
                return self._runner(
                    argv,
                    cwd=scratch,
                    input_text=stdin,
                    timeout_s=timeout_s,
                    env=env,
                )
            except subprocess.TimeoutExpired as exc:
                raise LLMTimeoutError(f"{self.name} timed out after {timeout_s}s.") from exc

    def is_available(self) -> bool:
        """Return whether the CLI binary is present and runnable.

        Runs the version command through the runner; ``True`` iff it exits ``0``.
        A missing binary (:class:`FileNotFoundError` / :class:`OSError`) yields
        ``False`` rather than raising.
        """
        try:
            result = self._run(
                [self._command, *self._version_argv()],
                stdin=None,
                timeout_s=30,
            )
        except OSError:
            return False
        return result.returncode == 0

    def complete(self, request: LLMRequest) -> LLMResponse:
        """Run ``request`` through the CLI and return the parsed response.

        Raises:
            LLMBackendError: If the CLI exits non-zero (subclasses may raise a
                more specific subclass via :meth:`_classify_error`).
            LLMTimeoutError: If the call exceeds ``request.timeout_s``.
        """
        argv = self._build_argv(request)
        result = self._run(
            argv,
            stdin=self._stdin_for(request),
            timeout_s=request.timeout_s,
            env=self._env_for(request),
        )
        if result.returncode != 0:
            self._classify_error(result)
        return self._parse_response(result, request)

    def stream(self, request: LLMRequest) -> Iterator[str]:
        """Yield the completed response text as a single chunk.

        Token-level streaming (the CLI's ``stream-json`` mode) is deferred; this
        default satisfies the :class:`~atlas.ai.base.LLMProvider` protocol.
        """
        yield self.complete(request).text

    @abstractmethod
    def _build_argv(self, request: LLMRequest) -> list[str]:
        """Return the full argv (including the command) for ``request``."""

    @abstractmethod
    def _parse_response(self, result: RunResult, request: LLMRequest) -> LLMResponse:
        """Map a successful :class:`RunResult` onto an :class:`LLMResponse`."""
