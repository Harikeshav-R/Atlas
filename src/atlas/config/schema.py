"""Typed schema for Atlas's ``config.toml``.

Only the sections Atlas consumes today are modelled — cross-platform behaviour
plus the ``[ai]`` backend selection, the ``[render]`` pipeline, the
``[tailoring]`` controls, the ``[discovery]`` daemon settings, and the
``[aggregators]`` key-gated job sources. Unknown keys and the not-yet-built
sections (the ``[integrations]`` and ``[notifications]`` blocks from PROJECT.md
§10) are **ignored** rather than rejected, so a user's fuller config still loads
while those features are built out in later phases.
Every field is defaulted, so a missing or empty config file yields a valid
default :class:`Config`.

Secrets never appear here: API keys and passwords live in the OS keychain and
the config references them only by handle (see :mod:`atlas.config.secrets`).
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "AdzunaConfig",
    "AggregatorsConfig",
    "AiBackends",
    "AiConfig",
    "ClaudeCodeBackend",
    "Config",
    "DiscoveryConfig",
    "HonestyLevel",
    "LoggingConfig",
    "OpenRouterBackend",
    "RenderConfig",
    "TailoringConfig",
    "UsajobsConfig",
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


class HonestyLevel(StrEnum):
    """How far tailoring may rephrase or infer beyond the master resume (§11).

    - ``strict``: select/reorder/reword existing facts only; introduce no skills
      or claims not present in the master resume.
    - ``reword_only``: same facts, but freer rephrasing for impact and keyword
      surfacing.
    - ``light_inference`` *(default)*: may infer clearly-adjacent skills and
      phrase aggressively for keyword match.
    """

    STRICT = "strict"
    REWORD_ONLY = "reword_only"
    LIGHT_INFERENCE = "light_inference"


class TailoringConfig(_Base):
    """The ``[tailoring]`` section: resume-tailoring controls (PROJECT.md §5.7, §11).

    Attributes:
        honesty_level: How far rewording/inference may go (see :class:`HonestyLevel`).
            Ships as ``light_inference`` (PROJECT.md §11's selected default), one
            setting away from ``strict``. Modelled here as global config; a
            per-profile override is a later refinement (§11).
        enforce_one_page: Whether to run the render-measure-trim loop that packs
            the tailored resume onto a single page (PROJECT.md §5.7 step 2). When
            ``False``, the resume is rendered once without trimming.
    """

    honesty_level: HonestyLevel = HonestyLevel.LIGHT_INFERENCE
    enforce_one_page: bool = True


class DiscoveryConfig(_Base):
    """The ``[discovery]`` section: the background daemon's polling (PROJECT.md §5.4).

    Attributes:
        poll_interval_minutes: How often the daemon's scheduled poll runs
            (PROJECT.md §10). The poll currently scores not-yet-scored postings in
            the background; discovery-source polling arrives with the ATS/aggregator
            adapters.
        enable_scraping: Whether ToS-risky mainstream-board scraping is allowed
            (PROJECT.md §5.4). Off by default; not consumed yet (scraping is a later,
            explicitly-opt-in phase), modelled now to match PROJECT.md §10.
    """

    poll_interval_minutes: int = 120
    enable_scraping: bool = False


class AdzunaConfig(_Base):
    """The ``[aggregators.adzuna]`` section: the Adzuna job-search API (§5.4-B).

    Adzuna is a **key-gated** aggregator: it needs a free ``app_id`` + ``app_key``,
    kept in the OS keychain and referenced here only by handle (never the key
    itself). The source stays inactive — shown as "needs API key" in
    ``atlas doctor`` — until both keys are stored (``atlas source key adzuna``).

    Attributes:
        enabled: Whether the discovery poll includes Adzuna searches.
        app_id_handle: Keyring handle for the Adzuna application id.
        app_key_handle: Keyring handle for the Adzuna application key.
        country: The Adzuna country code to search (e.g. ``"us"``, ``"gb"``).
    """

    enabled: bool = False
    app_id_handle: str = "adzuna_app_id"
    app_key_handle: str = "adzuna_app_key"
    country: str = "us"


class UsajobsConfig(_Base):
    """The ``[aggregators.usajobs]`` section: the USAJOBS API (§5.4-B).

    USAJOBS is a **key-gated** aggregator using header auth: a free API key
    (``Authorization-Key``) plus the registering email as the ``User-Agent``. The
    key lives in the OS keychain (handle only here); the non-secret email lives in
    config. Inactive until both are set.

    Attributes:
        enabled: Whether the discovery poll includes USAJOBS searches.
        email: The email registered with USAJOBS, sent as the ``User-Agent``
            (non-secret, so it lives in config rather than the keychain).
        api_key_handle: Keyring handle for the USAJOBS API key.
    """

    enabled: bool = False
    email: str = ""
    api_key_handle: str = "usajobs"


class AggregatorsConfig(_Base):
    """The ``[aggregators]`` table: per-provider key-gated aggregator settings."""

    adzuna: AdzunaConfig = Field(default_factory=AdzunaConfig)
    usajobs: UsajobsConfig = Field(default_factory=UsajobsConfig)


class Config(_Base):
    """The top-level Atlas configuration."""

    ai: AiConfig = Field(default_factory=AiConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    render: RenderConfig = Field(default_factory=RenderConfig)
    tailoring: TailoringConfig = Field(default_factory=TailoringConfig)
    discovery: DiscoveryConfig = Field(default_factory=DiscoveryConfig)
    aggregators: AggregatorsConfig = Field(default_factory=AggregatorsConfig)
