"""Coding-CLI subprocess adapters for the Atlas AI layer.

Backends in this package drive a locally installed coding CLI (Claude Code,
Codex, Antigravity) headlessly through the :class:`~atlas.ai.cli.runner.SubprocessRunner`
boundary and map its JSON envelope onto the shared
:class:`~atlas.ai.base.LLMResponse`. The subprocess boundary is injectable so the
default test suite never spawns a real CLI (AGENTS.md §6.2).

This package ships the subprocess runner boundary, the ``CliAdapter`` base
class, and the concrete :class:`~atlas.ai.cli.claude_code.ClaudeCodeAdapter`
(Atlas's default CLI backend). Codex and Antigravity adapters arrive in later
phases.
"""

from __future__ import annotations

from atlas.ai.cli.base import CliAdapter
from atlas.ai.cli.claude_code import ClaudeCodeAdapter
from atlas.ai.cli.runner import RunResult, SubprocessRunner, default_subprocess_runner

__all__ = [
    "ClaudeCodeAdapter",
    "CliAdapter",
    "RunResult",
    "SubprocessRunner",
    "default_subprocess_runner",
]
