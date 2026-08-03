"""Tests for TOML config load/save in :mod:`atlas.config.loader`."""

from __future__ import annotations

from pathlib import Path

import pytest

from atlas.config import Config, ConfigValidationError, load_config, save_config


def test_load_missing_file_returns_defaults(tmp_path: Path) -> None:
    result = load_config(tmp_path / "absent.toml")
    assert result == Config()


def test_load_valid_config(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    path.write_text(
        '[ai]\ndefault_backend = "openrouter"\ndaily_spend_cap_usd = 12.5\n',
        encoding="utf-8",
    )
    config = load_config(path)
    assert config.ai.default_backend == "openrouter"
    assert config.ai.daily_spend_cap_usd == 12.5


def test_load_ignores_unknown_sections(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    path.write_text(
        '[ai]\ndefault_backend = "claude_code"\n\n[tailoring]\nhonesty_level = "strict"\n',
        encoding="utf-8",
    )
    config = load_config(path)
    assert config.ai.default_backend == "claude_code"


def test_load_render_section(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    path.write_text(
        '[render]\nengine = "weasyprint"\nresume_theme = "compact"\n',
        encoding="utf-8",
    )
    config = load_config(path)
    assert config.render.engine == "weasyprint"
    assert config.render.resume_theme == "compact"


def test_load_malformed_toml_raises(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    path.write_text("this is = = not toml", encoding="utf-8")
    with pytest.raises(ConfigValidationError, match="not valid TOML"):
        load_config(path)


def test_load_invalid_value_type_raises(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    # daily_spend_cap_usd must be a number, not a string.
    path.write_text('[ai]\ndaily_spend_cap_usd = "lots"\n', encoding="utf-8")
    with pytest.raises(ConfigValidationError, match="failed validation"):
        load_config(path)


def test_save_then_load_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    original = Config.model_validate(
        {"ai": {"default_backend": "openrouter", "backends": {"claude_code": {"use_bare": True}}}}
    )
    save_config(original, path)
    assert path.exists()
    assert load_config(path) == original


def test_save_creates_parent_directory(tmp_path: Path) -> None:
    path = tmp_path / "nested" / "dir" / "config.toml"
    save_config(Config(), path)
    assert path.exists()


def test_saved_file_contains_no_secret_fields(tmp_path: Path) -> None:
    # The schema has no secret fields, so the persisted TOML references only a
    # keyring handle, never a key value.
    path = tmp_path / "config.toml"
    save_config(Config(), path)
    text = path.read_text(encoding="utf-8")
    assert "api_key_handle" in text
    assert "api_key " not in text
