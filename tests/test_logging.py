"""Tests for logging setup in :mod:`atlas.logging`."""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from atlas.logging import (
    ATLAS_LOG_LEVEL_ENV,
    get_logger,
    log_file,
    resolve_level,
    setup_logging,
)
from tests.conftest import FakeHandlerFactory, HandlerFactoryCall


def test_log_file_lives_under_state_dir(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("atlas.logging.state_dir", lambda: Path("/fake/state"))
    assert log_file() == Path("/fake/state/atlas.log")


# --- resolve_level: precedence + parsing matrix --------------------------------


def test_explicit_log_level_wins() -> None:
    # Explicit level beats verbose, env, and config.
    level = resolve_level(log_level="ERROR", verbose=2, env_level="INFO", config_level="DEBUG")
    assert level == logging.ERROR


def test_explicit_numeric_level_string() -> None:
    assert resolve_level(log_level="10") == logging.DEBUG


def test_invalid_explicit_level_falls_through_to_verbose() -> None:
    # A bad explicit value is skipped, not fatal; verbose is used next.
    assert resolve_level(log_level="nonsense", verbose=1) == logging.INFO


@pytest.mark.parametrize(
    ("verbose", "expected"),
    [(1, logging.INFO), (2, logging.DEBUG), (5, logging.DEBUG)],
)
def test_verbose_counts(verbose: int, expected: int) -> None:
    assert resolve_level(verbose=verbose) == expected


def test_env_level_used_when_no_explicit_or_verbose() -> None:
    assert resolve_level(env_level="debug") == logging.DEBUG


def test_invalid_env_level_falls_through_to_config() -> None:
    assert resolve_level(env_level="bogus", config_level="ERROR") == logging.ERROR


def test_config_level_used_as_last_named_source() -> None:
    assert resolve_level(config_level="WARNING") == logging.WARNING


def test_invalid_config_level_falls_back_to_default() -> None:
    assert resolve_level(config_level="???") == logging.WARNING


def test_default_when_nothing_set() -> None:
    assert resolve_level() == logging.WARNING


def test_empty_level_string_is_ignored() -> None:
    # Whitespace-only parses to None → next source (here, the default).
    assert resolve_level(log_level="   ") == logging.WARNING


# --- setup_logging: installs handlers via the injected factory -----------------


def test_setup_installs_console_and_file_handlers(tmp_path: Path) -> None:
    factory = FakeHandlerFactory()
    resolved = setup_logging(
        log_level="DEBUG",
        handler_factory=factory,
        log_path=tmp_path / "atlas.log",
    )
    atlas_logger = logging.getLogger("atlas")
    assert resolved == logging.DEBUG
    assert factory.calls == [
        HandlerFactoryCall(console_level=logging.DEBUG, log_path=tmp_path / "atlas.log")
    ]
    assert len(atlas_logger.handlers) == 2
    assert atlas_logger.propagate is False
    # The logger admits DEBUG because the file handler wants it.
    assert atlas_logger.level == logging.DEBUG


def test_setup_creates_missing_log_directory(tmp_path: Path) -> None:
    target = tmp_path / "nested" / "dir" / "atlas.log"
    setup_logging(handler_factory=FakeHandlerFactory(), log_path=target)
    assert target.parent.is_dir()


def test_setup_is_idempotent_no_duplicate_handlers(tmp_path: Path) -> None:
    log_path = tmp_path / "atlas.log"
    setup_logging(handler_factory=FakeHandlerFactory(), log_path=log_path)
    setup_logging(handler_factory=FakeHandlerFactory(), log_path=log_path)
    # A second call replaces Atlas's handlers rather than stacking them.
    assert len(logging.getLogger("atlas").handlers) == 2


def test_setup_preserves_foreign_handlers(tmp_path: Path) -> None:
    # A handler Atlas did not install (no managed flag) must survive re-setup.
    atlas_logger = logging.getLogger("atlas")
    foreign = logging.NullHandler()
    atlas_logger.addHandler(foreign)
    setup_logging(handler_factory=FakeHandlerFactory(), log_path=tmp_path / "atlas.log")
    assert foreign in atlas_logger.handlers
    # The foreign handler plus the two Atlas handlers.
    assert len(atlas_logger.handlers) == 3


def test_setup_without_file_only_installs_console(tmp_path: Path) -> None:
    setup_logging(
        log_level="INFO",
        file_enabled=False,
        handler_factory=FakeHandlerFactory(),
        log_path=tmp_path / "atlas.log",
    )
    atlas_logger = logging.getLogger("atlas")
    assert len(atlas_logger.handlers) == 1
    # With no file handler, the logger level is just the console level.
    assert atlas_logger.level == logging.INFO


def test_setup_reads_env_level(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(ATLAS_LOG_LEVEL_ENV, "DEBUG")
    resolved = setup_logging(handler_factory=FakeHandlerFactory(), log_path=tmp_path / "atlas.log")
    assert resolved == logging.DEBUG


def test_setup_defaults_log_path_to_log_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # No log_path → uses log_file() under a faked state dir.
    monkeypatch.setattr("atlas.logging.state_dir", lambda: tmp_path)
    setup_logging(handler_factory=FakeHandlerFactory())
    assert (tmp_path / "atlas.log").exists()


def test_get_logger_returns_namespaced_logger() -> None:
    assert get_logger("atlas.thing").name == "atlas.thing"
