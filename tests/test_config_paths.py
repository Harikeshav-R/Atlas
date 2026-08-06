"""Tests for cross-platform path resolution in :mod:`atlas.config.paths`."""

from __future__ import annotations

from pathlib import Path

import pytest

from atlas.config import (
    cache_dir,
    config_dir,
    config_file,
    data_dir,
    pid_file,
    socket_file,
    state_dir,
)


@pytest.mark.parametrize(
    ("func", "platformdirs_name"),
    [
        (config_dir, "user_config_dir"),
        (data_dir, "user_data_dir"),
        (cache_dir, "user_cache_dir"),
        (state_dir, "user_state_dir"),
    ],
)
def test_path_helper_uses_platformdirs_with_atlas_app_name(
    func: object,
    platformdirs_name: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    def fake(app_name: str) -> str:
        calls.append(app_name)
        return f"/fake/{app_name}/{platformdirs_name}"

    monkeypatch.setattr(f"atlas.config.paths.platformdirs.{platformdirs_name}", fake)
    result = func()  # type: ignore[operator]
    assert isinstance(result, Path)
    assert calls == ["atlas"]
    assert result == Path(f"/fake/atlas/{platformdirs_name}")


def test_config_file_lives_under_config_dir(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "atlas.config.paths.platformdirs.user_config_dir",
        lambda app_name: f"/fake/{app_name}/config",
    )
    assert config_file() == Path("/fake/atlas/config/config.toml")
    assert config_file().parent == config_dir()


def test_pid_file_lives_under_state_dir(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "atlas.config.paths.platformdirs.user_state_dir",
        lambda app_name: f"/fake/{app_name}/state",
    )
    assert pid_file() == Path("/fake/atlas/state/daemon.pid")
    assert pid_file().parent == state_dir()


def test_socket_file_lives_under_state_dir(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "atlas.config.paths.platformdirs.user_state_dir",
        lambda app_name: f"/fake/{app_name}/state",
    )
    assert socket_file() == Path("/fake/atlas/state/daemon.socket")
    assert socket_file().parent == state_dir()
