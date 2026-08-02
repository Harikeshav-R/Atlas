"""Atlas configuration and secrets.

Resolves cross-platform application paths (:mod:`platformdirs`), and — in later
phases of this package — loads a human-editable TOML ``config.toml`` and reads
secrets from the OS keychain (:mod:`keyring`) referenced by handle, so no secret
ever lives in the config file, logs, or the database (PROJECT.md §5.15, §12).
"""

from __future__ import annotations

from atlas.config.errors import (
    ConfigError,
    ConfigValidationError,
    KeyringUnavailableError,
)
from atlas.config.loader import load_config, save_config
from atlas.config.paths import (
    cache_dir,
    config_dir,
    config_file,
    data_dir,
    state_dir,
)
from atlas.config.schema import (
    AiBackends,
    AiConfig,
    ClaudeCodeBackend,
    Config,
    OpenRouterBackend,
)
from atlas.config.secrets import (
    KEYRING_PASSPHRASE_ENV,
    SecretStore,
    default_secret_store,
    resolve_api_key,
    select_backend,
)

__all__ = [
    "KEYRING_PASSPHRASE_ENV",
    "AiBackends",
    "AiConfig",
    "ClaudeCodeBackend",
    "Config",
    "ConfigError",
    "ConfigValidationError",
    "KeyringUnavailableError",
    "OpenRouterBackend",
    "SecretStore",
    "cache_dir",
    "config_dir",
    "config_file",
    "data_dir",
    "default_secret_store",
    "load_config",
    "resolve_api_key",
    "save_config",
    "select_backend",
    "state_dir",
]
