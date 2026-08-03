"""Typed schema for Atlas's ``config.toml``.

Only the sections Atlas consumes today are modelled — cross-platform behaviour
plus the ``[ai]`` backend selection and the ``[render]`` pipeline. Unknown keys
and the not-yet-built sections (the ``[tailoring]``, ``[discovery]``,
``[integrations]``, and ``[notifications]`` blocks from PROJECT.md §10) are
**ignored** rather than rejected, so a user's fuller config still loads while
those features are built out in later phases. Every field is defaulted, so a
missing or empty config file yields a valid default :class:`Config`.

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
    "LoggingConfig",
    "OpenRouterBackend",
    "RenderConfig",
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


class LoggingConfig(_Base):
    """The ``[logging]`` section: console level and rotating-file settings.

    ``level`` sets the **console** verbosity; the file handler always captures
    ``DEBUG`` and up when enabled. The CLI's ``--log-level``/``-v`` options and
    the ``ATLAS_LOG_LEVEL`` environment variable override ``level`` at runtime
    (see :func:`atlas.logging.resolve_level`).

    Attributes:
        level: Console log level name (e.g. ``"WARNING"``, ``"INFO"``).
        file_enabled: Whether to write the rotating log file under the state dir.
        max_bytes: Rotate the log file once it reaches this size in bytes.
        backup_count: Number of rotated log files to keep.
    """

    level: str = "WARNING"
    file_enabled: bool = True
    max_bytes: int = 1_000_000
    backup_count: int = 3


class RenderConfig(_Base):
    """The ``[render]`` section: the HTML/CSS → PDF pipeline (PROJECT.md §5.11).

    Attributes:
        engine: The PDF renderer backend. ``"weasyprint"`` (the pure-Python
            default) is implemented today; ``"chromium"`` (headless
            Playwright print-to-PDF) is a documented later option and is
            rejected with a clear error until it lands.
        resume_theme: The name of the resume theme directory under
            ``atlas/render/themes/``. Defaults to ``"jakes-resume"`` (the
            familiar Jake Gutierrez one-page layout).
        cover_theme: The cover-letter theme name. Not consumed yet (cover-letter
            rendering is a later step); modelled now to match PROJECT.md §10.
    """

    engine: str = "weasyprint"
    resume_theme: str = "jakes-resume"
    cover_theme: str = "matching"


class Config(_Base):
    """The top-level Atlas configuration."""

    ai: AiConfig = Field(default_factory=AiConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    render: RenderConfig = Field(default_factory=RenderConfig)
