"""Typed schema for Atlas's ``config.toml``.

Only the sections Atlas consumes today are modelled — cross-platform behaviour
plus the ``[ai]`` backend selection. Unknown keys and whole sections (the
``[render]``, ``[tailoring]``, ``[discovery]``, ``[integrations]``, and
``[notifications]`` blocks from PROJECT.md §10) are **ignored** rather than
rejected, so a user's fuller config still loads while those features are built
out in later phases. Every field is defaulted, so a missing or empty config file
yields a valid default :class:`Config`.

Secrets never appear here: API keys and passwords live in the OS keychain and
the config references them only by handle (see :mod:`atlas.config.secrets`).
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "AiBackends",
    "AiConfig",
    "ClaudeCodeBackend",
    "Config",
    "OpenRouterBackend",
]


class _Base(BaseModel):
    """Base model that ignores unknown keys (forward-compatible config)."""

    model_config = ConfigDict(extra="ignore")


class ClaudeCodeBackend(_Base):
    """Settings for the Claude Code CLI backend (``[ai.backends.claude_code]``)."""

    type: str = "cli"
    command: str = "claude"
    output_format: str = "json"
    use_bare: bool = False
    #: Keyring handle for the ``ANTHROPIC_API_KEY`` used only in ``--bare`` mode;
    #: never the key itself. Ignored when ``use_bare`` is ``False`` (Claude Code
    #: then uses the user's existing login).
    api_key_handle: str = "anthropic"


class OpenRouterBackend(_Base):
    """Settings for the OpenRouter API backend (``[ai.backends.openrouter]``)."""

    type: str = "api"
    model: str = "anthropic/claude-sonnet"
    #: Keyring handle for the API key — never the key itself.
    api_key_handle: str = "openrouter"


class AiBackends(_Base):
    """The ``[ai.backends]`` table: per-backend settings."""

    claude_code: ClaudeCodeBackend = Field(default_factory=ClaudeCodeBackend)
    openrouter: OpenRouterBackend = Field(default_factory=OpenRouterBackend)


class AiConfig(_Base):
    """The ``[ai]`` section: backend selection, failover, and spend controls."""

    default_backend: str = "claude_code"
    failover: list[str] = Field(default_factory=lambda: ["openrouter"])
    scoring_model_tier: str = "fast"
    daily_spend_cap_usd: float = 5.0
    backends: AiBackends = Field(default_factory=AiBackends)


class Config(_Base):
    """The top-level Atlas configuration."""

    ai: AiConfig = Field(default_factory=AiConfig)
