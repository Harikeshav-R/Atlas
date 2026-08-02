"""Keyring-backed secret storage and API-key resolution.

Secrets (API keys, IMAP/CalDAV passwords, OAuth tokens) never live in Atlas's
config file, logs, or database — they live in the OS keychain, addressed by a
string *handle*, and the config file references only the handle (PROJECT.md
§5.15, §12). This module wraps :mod:`keyring` behind a small
:class:`SecretStore` and provides the single :func:`resolve_api_key` path the AI
layer uses.

Backend selection is deliberately strict: an insecure plaintext backend is never
used silently. On a box with a real OS keychain (Windows Credential Manager,
macOS Keychain, Linux Secret Service/kwallet) that backend is used. On a headless
box with no keychain, Atlas falls back to an encrypted-file backend **only** when
a passphrase is supplied via the ``ATLAS_KEYRING_PASSWORD`` environment variable;
otherwise :class:`~atlas.config.errors.KeyringUnavailableError` is raised rather
than risk writing secrets in the clear.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Protocol, cast

from atlas.config.errors import KeyringUnavailableError
from atlas.config.paths import data_dir

if TYPE_CHECKING:
    from collections.abc import Callable

__all__ = [
    "KEYRING_PASSPHRASE_ENV",
    "KeyringBackend",
    "SecretStore",
    "resolve_api_key",
    "select_backend",
]

#: The keyring "service" all Atlas handles are namespaced under.
_SERVICE = "atlas"

#: Environment variable holding the passphrase for the encrypted-file fallback.
KEYRING_PASSPHRASE_ENV = "ATLAS_KEYRING_PASSWORD"

# Fully-qualified names of backends that must never be used to store secrets:
# ``PlaintextKeyring`` writes secrets to disk in the clear, and ``fail.Keyring``
# is the "no backend available" sentinel. Selection rejects both.
_INSECURE_BACKENDS = frozenset(
    {
        "keyrings.alt.file.PlaintextKeyring",
        "keyring.backends.fail.Keyring",
        "keyring.backends.null.Keyring",
    }
)


class KeyringBackend(Protocol):
    """The subset of the :mod:`keyring` backend API that Atlas relies on."""

    def get_password(self, service: str, username: str) -> str | None:
        """Return the stored secret for ``(service, username)`` or ``None``."""

    def set_password(self, service: str, username: str, password: str) -> None:
        """Store ``password`` for ``(service, username)``."""

    def delete_password(self, service: str, username: str) -> None:
        """Delete the secret stored for ``(service, username)``."""


def _backend_name(backend: object) -> str:
    """Return the fully-qualified class name of a keyring backend."""
    cls = type(backend)
    return f"{cls.__module__}.{cls.__qualname__}"


def _default_get_os_backend() -> object:  # pragma: no cover
    """Return the keyring library's auto-selected OS backend.

    Pragma'd: probes the real OS keyring, which the hermetic suite never touches
    (AGENTS.md §6.2); tests inject a fake backend instead.
    """
    import keyring

    return keyring.get_keyring()


def _default_make_encrypted(passphrase: str) -> object:  # pragma: no cover
    """Build an encrypted-file keyring unlocked by ``passphrase`` (no prompt).

    Pragma'd: constructs the real ``keyrings.alt`` encrypted-file backend, which
    the hermetic suite never touches (AGENTS.md §6.2); tests inject a fake.
    """
    from keyrings.alt.file import EncryptedKeyring  # type: ignore[import-untyped]

    backend = EncryptedKeyring()
    backend.file_path = str(data_dir() / "keyring.enc")
    backend.keyring_key = passphrase  # unlock non-interactively
    return backend


def select_backend(
    *,
    get_os_backend: Callable[[], object] = _default_get_os_backend,
    make_encrypted: Callable[[str], object] = _default_make_encrypted,
    passphrase: str | None = None,
) -> KeyringBackend:
    """Select a secure keyring backend, or raise if none is available.

    Prefers the OS keychain when it is a genuinely secure backend. If the only
    OS backend is insecure (plaintext) or absent (fail/null), falls back to the
    encrypted-file backend when ``passphrase`` is provided, and otherwise raises.

    Args:
        get_os_backend: Callable returning the OS keychain backend (injected in
            tests).
        make_encrypted: Callable building the encrypted-file backend from a
            passphrase (injected in tests).
        passphrase: Passphrase for the encrypted-file fallback; typically read
            from ``ATLAS_KEYRING_PASSWORD`` by :func:`default_secret_store`.

    Returns:
        A usable, secure :class:`KeyringBackend`.

    Raises:
        KeyringUnavailableError: If no secure OS keychain is available and no
            passphrase was supplied for the encrypted-file fallback.
    """
    os_backend = get_os_backend()
    if _backend_name(os_backend) not in _INSECURE_BACKENDS:
        return cast("KeyringBackend", os_backend)
    if passphrase:
        return cast("KeyringBackend", make_encrypted(passphrase))
    raise KeyringUnavailableError(
        "No secure OS keychain is available. Configure a system keyring, or set "
        f"{KEYRING_PASSPHRASE_ENV} to enable the encrypted-file fallback."
    )


class SecretStore:
    """Stores and retrieves secrets by handle in a keyring backend.

    Handles are namespaced under the ``atlas`` keyring service, so the handle
    ``"openrouter"`` maps to keyring identity ``("atlas", "openrouter")``.
    """

    def __init__(self, backend: KeyringBackend) -> None:
        """Wrap an injected keyring ``backend``."""
        self._backend = backend

    def get(self, handle: str) -> str | None:
        """Return the secret stored under ``handle``, or ``None`` if unset."""
        return self._backend.get_password(_SERVICE, handle)

    def set(self, handle: str, value: str) -> None:
        """Store ``value`` under ``handle``."""
        self._backend.set_password(_SERVICE, handle, value)

    def delete(self, handle: str) -> None:
        """Delete the secret stored under ``handle``."""
        self._backend.delete_password(_SERVICE, handle)


def default_secret_store(
    *,
    get_os_backend: Callable[[], object] = _default_get_os_backend,
    make_encrypted: Callable[[str], object] = _default_make_encrypted,
) -> SecretStore:
    """Build a :class:`SecretStore` on the auto-selected secure backend.

    Reads the encrypted-file passphrase from ``ATLAS_KEYRING_PASSWORD`` (used
    only when no secure OS keychain is available).
    """
    backend = select_backend(
        get_os_backend=get_os_backend,
        make_encrypted=make_encrypted,
        passphrase=os.environ.get(KEYRING_PASSPHRASE_ENV),
    )
    return SecretStore(backend)


def resolve_api_key(
    store: SecretStore,
    handle: str,
    *,
    env_var: str | None = None,
    allow_env_fallback: bool = True,
) -> str | None:
    """Resolve an API key from the keyring, optionally falling back to an env var.

    The keyring is always tried first. On a miss, and only when
    ``allow_env_fallback`` is true and ``env_var`` is given, the environment is
    consulted. Local providers pass ``allow_env_fallback=False`` so a paid cloud
    key can never leak to a local endpoint. The key is returned for direct use;
    it is never written into :data:`os.environ`.

    Args:
        store: The secret store to read from.
        handle: The keyring handle for this provider's key.
        env_var: Optional environment variable to fall back to.
        allow_env_fallback: Whether the env-var fallback is permitted.

    Returns:
        The resolved key, or ``None`` if neither source has it.
    """
    key = store.get(handle)
    if key is not None:
        return key
    if allow_env_fallback and env_var is not None:
        return os.environ.get(env_var)
    return None
