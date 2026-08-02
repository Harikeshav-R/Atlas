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

from atlas.ai.cli.base import CliAdapter, CliAvailability, parse_cli_version
from atlas.ai.cli.claude_code import (
    ANTHROPIC_API_KEY_ENV,
    ClaudeCodeAdapter,
    build_claude_code_provider,
)
from atlas.ai.cli.runner import RunResult, SubprocessRunner, default_subprocess_runner

__all__ = [
    "ANTHROPIC_API_KEY_ENV",
    "ClaudeCodeAdapter",
    "CliAdapter",
    "CliAvailability",
    "RunResult",
    "SubprocessRunner",
    "build_claude_code_provider",
    "default_subprocess_runner",
    "parse_cli_version",
]
