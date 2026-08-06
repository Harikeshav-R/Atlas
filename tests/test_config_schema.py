"""Tests for the config schema in :mod:`atlas.config.schema`."""

from __future__ import annotations

from atlas.config import AiConfig, ClaudeCodeBackend, Config, LoggingConfig
from atlas.config.schema import HonestyLevel


def test_config_defaults() -> None:
    config = Config()
    assert config.ai.default_backend == "claude_code"
    assert config.ai.failover == ["openrouter"]
    assert config.ai.scoring_model_tier == "fast"
    assert config.ai.daily_spend_cap_usd == 5.0


def test_backend_defaults() -> None:
    ai = AiConfig()
    assert ai.backends.claude_code == ClaudeCodeBackend(
        type="cli",
        command="claude",
        output_format="json",
        use_bare=False,
        api_key_handle="anthropic",
    )
    assert ai.backends.claude_code.api_key_handle == "anthropic"
    assert ai.backends.openrouter.api_key_handle == "openrouter"
    assert ai.backends.openrouter.model == "anthropic/claude-sonnet"


def test_claude_code_api_key_handle_override() -> None:
    backend = ClaudeCodeBackend.model_validate({"api_key_handle": "my-anthropic"})
    assert backend.api_key_handle == "my-anthropic"


def test_logging_defaults() -> None:
    config = Config()
    assert config.logging == LoggingConfig(
        level="WARNING",
        file_enabled=True,
        max_bytes=1_000_000,
        backup_count=3,
    )


def test_logging_values_override() -> None:
    config = Config.model_validate(
        {"logging": {"level": "DEBUG", "file_enabled": False, "backup_count": 5}}
    )
    assert config.logging.level == "DEBUG"
    assert config.logging.file_enabled is False
    assert config.logging.backup_count == 5
    # Unset fields keep their defaults.
    assert config.logging.max_bytes == 1_000_000


def test_failover_default_is_independent_per_instance() -> None:
    # A mutable default must not be shared across instances.
    first = Config()
    first.ai.failover.append("bedrock")
    assert Config().ai.failover == ["openrouter"]


def test_extra_keys_are_ignored() -> None:
    # Unknown keys and not-yet-built sections (future features) load without error.
    config = Config.model_validate(
        {
            "ai": {"default_backend": "claude_code", "unknown_key": 1},
            "integrations": {"calendar": {"type": "caldav"}},
        }
    )
    assert config.ai.default_backend == "claude_code"
    assert not hasattr(config, "integrations")


def test_render_defaults() -> None:
    render = Config().render
    assert render.engine == "weasyprint"
    assert render.resume_theme == "jakes-resume"
    assert render.cover_theme == "matching"


def test_render_section_loads() -> None:
    config = Config.model_validate({"render": {"engine": "chromium", "resume_theme": "compact"}})
    assert config.render.engine == "chromium"
    assert config.render.resume_theme == "compact"
    # Unset render keys keep their defaults.
    assert config.render.cover_theme == "matching"


def test_tailoring_defaults() -> None:
    tailoring = Config().tailoring
    assert tailoring.honesty_level is HonestyLevel.LIGHT_INFERENCE
    assert tailoring.enforce_one_page is True


def test_tailoring_section_loads() -> None:
    config = Config.model_validate(
        {"tailoring": {"honesty_level": "strict", "enforce_one_page": False}}
    )
    assert config.tailoring.honesty_level is HonestyLevel.STRICT
    assert config.tailoring.enforce_one_page is False


def test_discovery_defaults() -> None:
    discovery = Config().discovery
    assert discovery.poll_interval_minutes == 120
    assert discovery.enable_scraping is False


def test_discovery_section_loads() -> None:
    config = Config.model_validate(
        {"discovery": {"poll_interval_minutes": 30, "enable_scraping": True}}
    )
    assert config.discovery.poll_interval_minutes == 30
    assert config.discovery.enable_scraping is True


def test_aggregators_defaults() -> None:
    aggregators = Config().aggregators
    # Key-gated sources ship disabled, referencing keys only by handle.
    assert aggregators.adzuna.enabled is False
    assert aggregators.adzuna.app_id_handle == "adzuna_app_id"
    assert aggregators.adzuna.app_key_handle == "adzuna_app_key"
    assert aggregators.adzuna.country == "us"
    assert aggregators.usajobs.enabled is False
    assert aggregators.usajobs.email == ""
    assert aggregators.usajobs.api_key_handle == "usajobs"


def test_aggregators_section_loads() -> None:
    config = Config.model_validate(
        {
            "aggregators": {
                "adzuna": {"enabled": True, "country": "gb"},
                "usajobs": {"enabled": True, "email": "sam@example.test"},
            }
        }
    )
    assert config.aggregators.adzuna.enabled is True
    assert config.aggregators.adzuna.country == "gb"
    # Unset handles keep their defaults.
    assert config.aggregators.adzuna.app_id_handle == "adzuna_app_id"
    assert config.aggregators.usajobs.enabled is True
    assert config.aggregators.usajobs.email == "sam@example.test"


def test_notifications_defaults() -> None:
    notifications = Config().notifications
    # Ships disabled — a fresh install is quiet until the user opts in.
    assert notifications.enabled is False
    assert notifications.min_match_score == 80
    assert notifications.deadline_lead_hours == 24
    assert notifications.quiet_hours == "22:00-08:00"
    assert notifications.daily_cap == 20


def test_notifications_section_loads() -> None:
    config = Config.model_validate(
        {
            "notifications": {
                "enabled": True,
                "min_match_score": 90,
                "deadline_lead_hours": 12,
                "quiet_hours": "",
                "daily_cap": 5,
            }
        }
    )
    assert config.notifications.enabled is True
    assert config.notifications.min_match_score == 90
    assert config.notifications.deadline_lead_hours == 12
    assert config.notifications.quiet_hours == ""
    assert config.notifications.daily_cap == 5


def test_values_override_defaults() -> None:
    config = Config.model_validate(
        {
            "ai": {
                "default_backend": "openrouter",
                "daily_spend_cap_usd": 10.0,
                "backends": {"claude_code": {"use_bare": True}},
            }
        }
    )
    assert config.ai.default_backend == "openrouter"
    assert config.ai.daily_spend_cap_usd == 10.0
    assert config.ai.backends.claude_code.use_bare is True
