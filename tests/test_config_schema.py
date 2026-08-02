"""Tests for the config schema in :mod:`atlas.config.schema`."""

from __future__ import annotations

from atlas.config import AiConfig, ClaudeCodeBackend, Config


def test_config_defaults() -> None:
    config = Config()
    assert config.ai.default_backend == "claude_code"
    assert config.ai.failover == ["openrouter"]
    assert config.ai.scoring_model_tier == "fast"
    assert config.ai.daily_spend_cap_usd == 5.0


def test_backend_defaults() -> None:
    ai = AiConfig()
    assert ai.backends.claude_code == ClaudeCodeBackend(
        type="cli", command="claude", output_format="json", use_bare=False
    )
    assert ai.backends.openrouter.api_key_handle == "openrouter"
    assert ai.backends.openrouter.model == "anthropic/claude-sonnet"


def test_failover_default_is_independent_per_instance() -> None:
    # A mutable default must not be shared across instances.
    first = Config()
    first.ai.failover.append("bedrock")
    assert Config().ai.failover == ["openrouter"]


def test_extra_keys_are_ignored() -> None:
    # Unknown keys and whole sections (future features) load without error.
    config = Config.model_validate(
        {
            "ai": {"default_backend": "claude_code", "unknown_key": 1},
            "render": {"engine": "weasyprint"},
        }
    )
    assert config.ai.default_backend == "claude_code"
    assert not hasattr(config, "render")


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
