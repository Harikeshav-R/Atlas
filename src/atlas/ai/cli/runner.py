"""The subprocess boundary for coding-CLI adapters.

Coding-CLI backends (:mod:`atlas.ai.cli`) drive an external binary such as
``claude`` via a child process. To keep that I/O boundary injectable — and the
default test suite hermetic (no real process ever spawned, per AGENTS.md §6.2) —
adapters depend on the :class:`SubprocessRunner` protocol rather than calling
:mod:`subprocess` directly. Production wiring uses
:func:`default_subprocess_runner`; tests inject a fake runner that replays
scripted :class:`RunResult` values.
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

__all__ = ["RunResult", "SubprocessRunner", "default_subprocess_runner"]


@dataclass(frozen=True)
class RunResult:
    """The captured outcome of a finished child process.

    Attributes:
        returncode: The process exit code (``0`` conventionally means success).
        stdout: Everything the process wrote to standard output.
        stderr: Everything the process wrote to standard error, captured
            separately so diagnostics never contaminate the parsed answer.
    """

    returncode: int
    stdout: str
    stderr: str


@runtime_checkable
class SubprocessRunner(Protocol):
    """Callable that runs a child process to completion and captures its output.

    Implementations must capture ``stdout`` and ``stderr`` separately and, when
    ``timeout_s`` is exceeded, terminate the child's whole process tree and
    raise :class:`subprocess.TimeoutExpired`. A missing binary surfaces as the
    usual :class:`FileNotFoundError` / :class:`OSError`.
    """

    def __call__(
        self,
        argv: Sequence[str],
        *,
        cwd: str | None,
        input_text: str | None,
        timeout_s: int,
        env: Mapping[str, str] | None,
    ) -> RunResult:
        """Run ``argv`` and return its :class:`RunResult`."""


def default_subprocess_runner(  # pragma: no cover
    argv: Sequence[str],
    *,
    cwd: str | None,
    input_text: str | None,
    timeout_s: int,
    env: Mapping[str, str] | None,
) -> RunResult:
    """Run ``argv`` in a child process, killing the whole tree on timeout.

    The child is started in its own process group/session so that, on timeout,
    the entire tree can be terminated rather than leaking orphaned grandchildren.
    Text is decoded as UTF-8 with ``errors="replace"`` so undecodable diagnostic
    bytes never crash the caller.

    This thin subprocess boundary carries ``# pragma: no cover`` because the
    default test suite never spawns a real process (AGENTS.md §6.2) and the
    OS-specific process-group kill cannot be covered uniformly across the CI OS
    matrix; adapters are exercised through an injected fake runner instead.

    Raises:
        subprocess.TimeoutExpired: If the child does not finish within
            ``timeout_s`` seconds (after the process tree has been killed).
    """
    process = subprocess.Popen(
        list(argv),
        cwd=cwd,
        env=dict(env) if env is not None else None,
        stdin=subprocess.PIPE if input_text is not None else None,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        start_new_session=True,
    )
    try:
        stdout, stderr = process.communicate(input=input_text, timeout=timeout_s)
    except subprocess.TimeoutExpired:
        # On POSIX, kill the whole process group so orphaned grandchildren don't
        # leak; on Windows (no process groups here) fall back to killing the child.
        if sys.platform != "win32":
            try:
                os.killpg(os.getpgid(process.pid), signal.SIGKILL)
            except OSError:
                process.kill()
        else:
            process.kill()
        process.communicate()
        raise
    return RunResult(returncode=process.returncode, stdout=stdout, stderr=stderr)
