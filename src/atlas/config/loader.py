"""Load and save Atlas's ``config.toml``.

Reading uses the standard-library :mod:`tomllib` (Python 3.11+); writing uses
:mod:`tomli_w`. A missing config file is not an error — it yields a default
:class:`~atlas.config.schema.Config`. Parse and validation failures are wrapped
as :class:`~atlas.config.errors.ConfigValidationError` so callers catch a single
Atlas type. Secrets are never part of the schema, so :func:`save_config` cannot
write one to disk.
"""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import TYPE_CHECKING

import tomli_w
from pydantic import ValidationError

from atlas.config.errors import ConfigValidationError
from atlas.config.paths import config_file
from atlas.config.schema import Config

if TYPE_CHECKING:
    from collections.abc import Mapping

__all__ = ["load_config", "save_config"]


def load_config(path: Path | None = None) -> Config:
    """Load and validate the config file, returning defaults when it is absent.

    Args:
        path: The config file to read; defaults to
            :func:`atlas.config.paths.config_file`.

    Returns:
        The validated :class:`Config` (all-default when the file is missing).

    Raises:
        ConfigValidationError: If the file is not valid TOML or fails schema
            validation.
    """
    target = path if path is not None else config_file()
    if not target.exists():
        return Config()
    try:
        with target.open("rb") as handle:
            raw = tomllib.load(handle)
    except tomllib.TOMLDecodeError as exc:
        raise ConfigValidationError(f"Config file is not valid TOML: {target}") from exc
    try:
        return Config.model_validate(raw)
    except ValidationError as exc:
        raise ConfigValidationError(f"Config file failed validation: {target}") from exc


def save_config(config: Config, path: Path | None = None) -> None:
    """Serialize ``config`` to TOML, creating the parent directory as needed.

    Args:
        config: The configuration to persist.
        path: The destination file; defaults to
            :func:`atlas.config.paths.config_file`.
    """
    target = path if path is not None else config_file()
    target.parent.mkdir(parents=True, exist_ok=True)
    data: Mapping[str, object] = config.model_dump(mode="json")
    with target.open("wb") as handle:
        tomli_w.dump(data, handle)
