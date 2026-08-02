"""Error hierarchy for the Atlas configuration layer."""

from __future__ import annotations

__all__ = ["ConfigError", "ConfigValidationError", "KeyringUnavailableError"]


class ConfigError(Exception):
    """Base class for every error raised by :mod:`atlas.config`."""


class ConfigValidationError(ConfigError):
    """Raised when a config file cannot be parsed or fails schema validation.

    Wraps the underlying ``tomllib.TOMLDecodeError`` or Pydantic
    ``ValidationError`` so callers catch a single Atlas type.
    """


class KeyringUnavailableError(ConfigError):
    """Raised when no usable keyring backend can be selected.

    Neither an OS keychain nor the encrypted-file fallback was available, so
    secrets cannot be stored or read.
    """
