"""Logging setup for Atlas.

Atlas logs diagnostics for operators and the future background daemon while
keeping user-facing output clean (``docs/agent/coding-standards.md`` "Errors &
logging": log details daemon-/CLI-side, surface generic messages, never leak
secrets or paths). This module configures the ``"atlas"`` package logger with two
handlers: a :class:`~rich.logging.RichHandler` on the shared **stderr** console
(so records never contaminate stdout that a caller may be piping, e.g. ``--json``)
and a rotating **file** handler under the platformdirs state dir
(:func:`atlas.config.state_dir`) that captures ``DEBUG`` and up.

The design separates a **pure** level-resolution step (:func:`resolve_level`,
fully testable) from the **impure** handler installation
(:func:`setup_logging`), whose real-I/O boundary — building the Rich/file
handlers — is an injectable factory defaulting to a pragma'd builder, so the
hermetic suite installs a fake and never writes a real log file or opens the real
console (AGENTS.md §6.2).

Modules obtain a logger with ``logging.getLogger(__name__)`` (namespaced under
``atlas.*``); :func:`setup_logging` configures the shared ``"atlas"`` ancestor and
sets ``propagate=False`` so records do not reach the root logger.
"""

from __future__ import annotations

import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

from rich.logging import RichHandler

from atlas.cli.console import error_console
from atlas.config.paths import state_dir

if TYPE_CHECKING:
    from collections.abc import Sequence

__all__ = [
    "ATLAS_LOG_LEVEL_ENV",
    "HandlerFactory",
    "get_logger",
    "log_file",
    "resolve_level",
    "setup_logging",
]

#: The logger namespace Atlas configures; every module's ``getLogger(__name__)``
#: descends from it.
_ROOT_LOGGER_NAME = "atlas"

#: Environment variable that overrides the configured console level.
ATLAS_LOG_LEVEL_ENV = "ATLAS_LOG_LEVEL"

#: Console level when nothing else selects one (quiet by default).
_DEFAULT_CONSOLE_LEVEL = logging.WARNING

#: Console levels stepped into by ``-v`` / ``-vv`` (further ``-v`` stays at DEBUG).
_VERBOSE_LEVELS = (logging.INFO, logging.DEBUG)

#: Name of the log file within the state dir.
_LOG_FILENAME = "atlas.log"

#: Marks handlers installed by :func:`setup_logging` so repeat calls replace only
#: Atlas's own handlers (idempotence) without disturbing any others.
_ATLAS_HANDLER_FLAG = "_atlas_managed"

# Module logger (configured by setup_logging like any other atlas.* logger).
logger = logging.getLogger(__name__)


class HandlerFactory(Protocol):
    """Builds the handlers :func:`setup_logging` installs (an injectable seam)."""

    def __call__(self, *, console_level: int, log_path: Path) -> Sequence[logging.Handler]:
        """Return the handlers to attach to the ``"atlas"`` logger."""


def log_file() -> Path:
    """Return the path to Atlas's log file inside the state dir.

    Pure — computes the path without creating anything (mirrors
    :func:`atlas.db.engine.db_path`). :func:`setup_logging` creates the parent
    directory when it installs the file handler.
    """
    return state_dir() / _LOG_FILENAME


def _parse_level(value: str) -> int | None:
    """Return the numeric log level for a name/number ``value``, or ``None``.

    Accepts a level name (case-insensitive, e.g. ``"debug"``) or a numeric
    string (e.g. ``"10"``). Any unrecognized value yields ``None`` so the caller
    can fall back rather than crash.
    """
    candidate = value.strip()
    if not candidate:
        return None
    if candidate.isdigit():
        return int(candidate)
    resolved = logging.getLevelName(candidate.upper())
    # ``getLevelName`` returns an ``int`` for known names and the string
    # ``"Level <x>"`` for unknown ones.
    return resolved if isinstance(resolved, int) else None


def resolve_level(
    *,
    log_level: str | None = None,
    verbose: int = 0,
    env_level: str | None = None,
    config_level: str | None = None,
) -> int:
    """Resolve the console log level from all sources, highest precedence first.

    Precedence: an explicit ``log_level`` (e.g. ``--log-level``) wins, then a
    ``verbose`` count (``-v`` → INFO, ``-vv`` and beyond → DEBUG), then the
    ``ATLAS_LOG_LEVEL`` value in ``env_level``, then the config file's
    ``config_level``, then the default (:data:`logging.WARNING`). A malformed
    level string at any tier is skipped in favor of the next source, so a bad
    value never crashes the CLI.

    Args:
        log_level: Explicit level name/number, or ``None``.
        verbose: Count of ``-v`` flags (``0`` means "not set").
        env_level: Value of the ``ATLAS_LOG_LEVEL`` environment variable, or
            ``None``.
        config_level: Level from the ``[logging]`` config section, or ``None``.

    Returns:
        The resolved numeric level.
    """
    if log_level is not None:
        parsed = _parse_level(log_level)
        if parsed is not None:
            return parsed
    if verbose > 0:
        return _VERBOSE_LEVELS[min(verbose, len(_VERBOSE_LEVELS)) - 1]
    if env_level is not None:
        parsed = _parse_level(env_level)
        if parsed is not None:
            return parsed
    if config_level is not None:
        parsed = _parse_level(config_level)
        if parsed is not None:
            return parsed
    return _DEFAULT_CONSOLE_LEVEL


def _default_handler_factory(  # pragma: no cover - opens the real console/log file (AGENTS.md §6.2)
    *, console_level: int, log_path: Path
) -> Sequence[logging.Handler]:
    """Build the real console + rotating-file handlers.

    Pragma'd: constructs a live :class:`~rich.logging.RichHandler` on the shared
    stderr console and opens the on-disk rotating log file, neither of which the
    hermetic suite touches; tests inject a fake factory instead.
    """
    console = RichHandler(
        console=error_console,
        level=console_level,
        show_time=True,
        show_path=False,
    )
    file_handler = RotatingFileHandler(
        log_path,
        maxBytes=1_000_000,
        backupCount=3,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    return (console, file_handler)


def setup_logging(
    *,
    log_level: str | None = None,
    verbose: int = 0,
    config_level: str | None = None,
    file_enabled: bool = True,
    handler_factory: HandlerFactory = _default_handler_factory,
    log_path: Path | None = None,
) -> int:
    """Configure the ``"atlas"`` logger and return the resolved console level.

    Idempotent: each call removes handlers installed by a previous call before
    adding fresh ones, so repeated invocation never stacks duplicates. The
    ``"atlas"`` logger is set to ``propagate=False`` and to the most verbose of
    the console and (when enabled) the ``DEBUG`` file level, so both handlers see
    everything they should while the root logger stays untouched.

    Args:
        log_level: Explicit console level (``--log-level``), or ``None``.
        verbose: Count of ``-v`` flags.
        config_level: Console level from the ``[logging]`` config section.
        file_enabled: Whether to install the rotating file handler.
        handler_factory: Builds the handlers to install; injected in tests.
        log_path: Log-file path; defaults to :func:`log_file`. Its parent
            directory is created if absent.

    Returns:
        The resolved numeric console level.
    """
    console_level = resolve_level(
        log_level=log_level,
        verbose=verbose,
        env_level=os.environ.get(ATLAS_LOG_LEVEL_ENV),
        config_level=config_level,
    )
    target = log_path if log_path is not None else log_file()
    target.parent.mkdir(parents=True, exist_ok=True)

    atlas_logger = logging.getLogger(_ROOT_LOGGER_NAME)
    atlas_logger.propagate = False
    # Remove only handlers we installed previously (idempotent re-setup).
    for existing in list(atlas_logger.handlers):
        if getattr(existing, _ATLAS_HANDLER_FLAG, False):
            atlas_logger.removeHandler(existing)
            existing.close()

    handlers = handler_factory(console_level=console_level, log_path=target)
    file_installed = False
    for handler in handlers:
        if isinstance(handler, logging.FileHandler):
            if not file_enabled:
                handler.close()
                continue
            file_installed = True
        setattr(handler, _ATLAS_HANDLER_FLAG, True)
        atlas_logger.addHandler(handler)

    # The logger gates records before any handler sees them, so it must admit the
    # most verbose level wanted: the console level, or DEBUG when the file handler
    # (which captures DEBUG+) is installed.
    atlas_logger.setLevel(min(console_level, logging.DEBUG) if file_installed else console_level)
    return console_level


def get_logger(name: str) -> logging.Logger:
    """Return the ``logging.Logger`` for ``name`` (an ``atlas.*`` module name).

    A thin convenience over :func:`logging.getLogger` for discoverability; every
    such logger descends from the ``"atlas"`` logger configured by
    :func:`setup_logging`.
    """
    return logging.getLogger(name)
