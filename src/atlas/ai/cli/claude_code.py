"""The Claude Code CLI adapter — Atlas's default coding-CLI backend.

Drives the local ``claude`` binary in headless print mode
(``claude -p ... --output-format json --json-schema ...``) and maps its JSON
envelope onto :class:`~atlas.ai.base.LLMResponse`. See ``docs/PROJECT.md``
Appendix A.1 and ``docs/cli-reference/claude-code.md``.

By default the adapter uses the user's existing Claude Code login and passes no
``--allowedTools`` (nothing is auto-approved); the base runs each call in a
throwaway scratch directory so project ``CLAUDE.md``/hooks are never picked up.
Setting ``use_bare=True`` switches to ``--bare`` (skips OAuth/keychain) and
requires an injected ``ANTHROPIC_API_KEY``.
"""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, NoReturn

from atlas.ai.base import (
    LLMAuthError,
    LLMBackendError,
    LLMRateLimitError,
    LLMRequest,
    LLMResponse,
    Usage,
)
from atlas.ai.cli.base import CliAdapter
from atlas.ai.cli.runner import RunResult, SubprocessRunner, default_subprocess_runner
from atlas.config.secrets import resolve_api_key

if TYPE_CHECKING:
    from atlas.config.schema import ClaudeCodeBackend
    from atlas.config.secrets import SecretStore

__all__ = ["ANTHROPIC_API_KEY_ENV", "ClaudeCodeAdapter", "build_claude_code_provider"]

#: Environment variable consulted as a fallback when the keyring has no bare-mode key.
ANTHROPIC_API_KEY_ENV = "ANTHROPIC_API_KEY"

# Case-insensitive stderr substrings used to classify a failed invocation. Claude
# Code only exposes structured error categories in stream-json mode, so plain
# --output-format json runs fall back to matching diagnostic text; this heuristic
# is refined once stream-json / ``atlas doctor`` can read the real category.
_AUTH_MARKERS = ("authentication", "unauthorized", "not logged in", "oauth", "api key", "401")
_RATE_LIMIT_MARKERS = ("rate limit", "429", "overloaded", "quota", "billing")

# Appended to the caller's system prompt to keep Claude in a text/JSON-only mode.
_NEUTRALIZE_INSTRUCTION = "Respond directly with the answer only; do not use any tools."


class ClaudeCodeAdapter(CliAdapter):
    """:class:`~atlas.ai.base.LLMProvider` backed by the ``claude`` CLI."""

    name = "claude_code"

    def __init__(
        self,
        *,
        command: str = "claude",
        runner: SubprocessRunner,
        use_bare: bool = False,
        api_key: str | None = None,
        model: str | None = None,
    ) -> None:
        """Configure the adapter.

        Args:
            command: The ``claude`` executable (name on ``PATH`` or a path).
            runner: The injected subprocess boundary (never touches the real
                process in tests).
            use_bare: If ``True``, pass ``--bare`` and authenticate via an
                injected ``ANTHROPIC_API_KEY`` instead of the existing login.
            api_key: The Anthropic API key for bare mode. Injected (from the
                keyring/config), never read from Atlas's own environment and
                never logged. Required when ``use_bare`` is ``True``.
            model: Optional model slug to pass via ``--model``.

        Raises:
            LLMAuthError: If ``use_bare`` is ``True`` but no ``api_key`` was given.
        """
        super().__init__(command=command, runner=runner)
        if use_bare and api_key is None:
            raise LLMAuthError("Claude Code bare mode requires an API key.")
        self._use_bare = use_bare
        self._api_key = api_key
        self._model = model

    def _build_argv(self, request: LLMRequest) -> list[str]:
        """Assemble the ``claude`` argv for ``request`` (no ``--allowedTools``)."""
        argv = [self._command]
        if self._use_bare:
            argv.append("--bare")
        argv += ["-p", request.prompt, "--output-format", "json"]
        system = self._system_prompt(request)
        argv += ["--append-system-prompt", system]
        if request.response_schema is not None:
            argv += ["--json-schema", json.dumps(request.response_schema)]
        if self._model is not None:
            argv += ["--model", self._model]
        return argv

    def _system_prompt(self, request: LLMRequest) -> str:
        """Return the system prompt, always carrying the neutralize instruction."""
        if request.system is None:
            return _NEUTRALIZE_INSTRUCTION
        return f"{request.system}\n\n{_NEUTRALIZE_INSTRUCTION}"

    def _env_for(self, request: LLMRequest) -> Mapping[str, str] | None:
        """Return the child environment, injecting the API key in bare mode.

        The key is merged onto a copy of the inherited environment (an explicit
        env replaces the child's whole environment) so ``PATH`` and friends are
        preserved. Non-bare mode inherits the environment unchanged.
        """
        if not self._use_bare:
            return None
        env = dict(os.environ)
        # ``api_key`` is guaranteed non-None in bare mode by ``__init__``.
        assert self._api_key is not None
        env["ANTHROPIC_API_KEY"] = self._api_key
        return env

    def _classify_error(self, result: RunResult) -> NoReturn:
        """Raise a specific error based on the CLI's stderr diagnostics.

        Heuristic: match diagnostic text since plain JSON mode exposes no
        structured error category (refined when stream-json / ``atlas doctor``
        lands). Messages stay generic so stderr, paths, and secrets never leak.
        """
        stderr = result.stderr.lower()
        if any(marker in stderr for marker in _AUTH_MARKERS):
            raise LLMAuthError(f"{self.name} authentication failed.")
        if any(marker in stderr for marker in _RATE_LIMIT_MARKERS):
            raise LLMRateLimitError(f"{self.name} was rate-limited or over quota.")
        raise LLMBackendError(f"{self.name} exited with code {result.returncode}.")

    def _parse_response(self, result: RunResult, request: LLMRequest) -> LLMResponse:
        """Map the ``claude`` JSON envelope onto an :class:`LLMResponse`."""
        try:
            envelope: dict[str, Any] = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            raise LLMBackendError(f"{self.name} returned unparseable output.") from exc
        usage_obj = envelope.get("usage") or {}
        usage = Usage(
            input_tokens=usage_obj.get("input_tokens"),
            output_tokens=usage_obj.get("output_tokens"),
            total_tokens=usage_obj.get("total_tokens"),
            cost_usd=envelope.get("total_cost_usd"),
        )
        return LLMResponse(
            text=envelope.get("result", ""),
            structured=envelope.get("structured_output"),
            raw=envelope,
            usage=usage,
            model=envelope.get("model") or self._model or self.name,
            backend=self.name,
        )


def build_claude_code_provider(
    config: ClaudeCodeBackend,
    store: SecretStore,
    *,
    runner: SubprocessRunner = default_subprocess_runner,
) -> ClaudeCodeAdapter:
    """Build a :class:`ClaudeCodeAdapter` from config + keyring.

    In ``--bare`` mode the adapter needs an ``ANTHROPIC_API_KEY``; this resolves
    it from ``store`` under the configured handle (falling back to the
    ``ANTHROPIC_API_KEY`` environment variable) and passes it to the adapter
    directly, never via :data:`os.environ`. In non-bare mode no key is resolved
    or passed — Claude Code uses the user's existing login.

    Args:
        config: The ``[ai.backends.claude_code]`` settings (command, bare flag,
            key handle).
        store: The secret store to resolve the bare-mode key from.
        runner: The injected subprocess boundary; defaults to the real
            process-spawning runner and is replaced by a fake in tests.

    Returns:
        A configured adapter ready to
        :meth:`~atlas.ai.cli.base.CliAdapter.complete`.

    Raises:
        LLMAuthError: If ``use_bare`` is set but no key can be resolved (raised
            by :class:`ClaudeCodeAdapter`).
    """
    api_key = (
        resolve_api_key(
            store,
            config.api_key_handle,
            env_var=ANTHROPIC_API_KEY_ENV,
            allow_env_fallback=True,
        )
        if config.use_bare
        else None
    )
    return ClaudeCodeAdapter(
        command=config.command,
        runner=runner,
        use_bare=config.use_bare,
        api_key=api_key,
    )
