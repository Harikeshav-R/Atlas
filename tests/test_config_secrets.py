"""Tests for keyring secret storage and API-key resolution in :mod:`atlas.config.secrets`."""

from __future__ import annotations

import pytest

from atlas.config import (
    KEYRING_PASSPHRASE_ENV,
    KeyringUnavailableError,
    SecretStore,
    default_secret_store,
    resolve_api_key,
    select_backend,
)
from atlas.config.secrets import KeyringBackend
from tests.conftest import FakeKeyring, named_keyring

# --- SecretStore ---------------------------------------------------------------


def test_secret_store_round_trip(fake_keyring: FakeKeyring) -> None:
    store = SecretStore(fake_keyring)
    assert store.get("openrouter") is None
    store.set("openrouter", "fake-secret-value")
    assert store.get("openrouter") == "fake-secret-value"
    # Namespaced under the "atlas" service.
    assert fake_keyring.get_password("atlas", "openrouter") == "fake-secret-value"


def test_secret_store_delete(fake_keyring: FakeKeyring) -> None:
    store = SecretStore(fake_keyring)
    store.set("openrouter", "fake-secret-value")
    store.delete("openrouter")
    assert store.get("openrouter") is None


def test_fake_keyring_satisfies_backend_protocol(fake_keyring: FakeKeyring) -> None:
    # Structural check: the fake matches what SecretStore requires.
    backend: KeyringBackend = fake_keyring
    assert backend.get_password("atlas", "missing") is None


# --- select_backend ------------------------------------------------------------


def test_select_backend_uses_secure_os_keychain() -> None:
    secure = named_keyring("some.os.SecureKeychain")
    backend = select_backend(get_os_backend=lambda: secure)
    assert backend is secure


def test_select_backend_falls_back_to_encrypted_when_insecure() -> None:
    insecure = named_keyring("keyrings.alt.file.PlaintextKeyring")
    encrypted = FakeKeyring()
    made: list[str] = []

    def make_encrypted(passphrase: str) -> object:
        made.append(passphrase)
        return encrypted

    backend = select_backend(
        get_os_backend=lambda: insecure,
        make_encrypted=make_encrypted,
        passphrase="pw",
    )
    assert backend is encrypted
    assert made == ["pw"]


def test_select_backend_rejects_fail_backend_without_passphrase() -> None:
    unusable = named_keyring("keyring.backends.fail.Keyring")
    with pytest.raises(KeyringUnavailableError, match="No secure OS keychain"):
        select_backend(get_os_backend=lambda: unusable)


def test_select_backend_rejects_plaintext_without_passphrase() -> None:
    insecure = named_keyring("keyrings.alt.file.PlaintextKeyring")
    with pytest.raises(KeyringUnavailableError, match=KEYRING_PASSPHRASE_ENV):
        select_backend(get_os_backend=lambda: insecure, passphrase=None)


# --- default_secret_store ------------------------------------------------------


def test_default_secret_store_reads_passphrase_from_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    insecure = named_keyring("keyrings.alt.file.PlaintextKeyring")
    encrypted = FakeKeyring()
    monkeypatch.setenv(KEYRING_PASSPHRASE_ENV, "env-pass")
    seen: list[str] = []

    def make_encrypted(passphrase: str) -> object:
        seen.append(passphrase)
        return encrypted

    store = default_secret_store(
        get_os_backend=lambda: insecure,
        make_encrypted=make_encrypted,
    )
    assert isinstance(store, SecretStore)
    assert seen == ["env-pass"]


def test_default_secret_store_raises_without_env_passphrase(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    insecure = named_keyring("keyrings.alt.file.PlaintextKeyring")
    monkeypatch.delenv(KEYRING_PASSPHRASE_ENV, raising=False)
    with pytest.raises(KeyringUnavailableError):
        default_secret_store(get_os_backend=lambda: insecure)


# --- resolve_api_key -----------------------------------------------------------


def test_resolve_api_key_reads_from_keyring(fake_keyring: FakeKeyring) -> None:
    store = SecretStore(fake_keyring)
    store.set("openrouter", "keyring-value")
    assert resolve_api_key(store, "openrouter", env_var="OPENROUTER_KEY") == "keyring-value"


def test_resolve_api_key_env_fallback_on_miss(
    fake_keyring: FakeKeyring, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OPENROUTER_KEY", "env-value")
    store = SecretStore(fake_keyring)
    assert resolve_api_key(store, "openrouter", env_var="OPENROUTER_KEY") == "env-value"


def test_resolve_api_key_no_env_fallback_for_local_providers(
    fake_keyring: FakeKeyring, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A paid cloud key must never leak to a local endpoint.
    monkeypatch.setenv("OPENROUTER_KEY", "env-value")
    store = SecretStore(fake_keyring)
    assert (
        resolve_api_key(store, "ollama", env_var="OPENROUTER_KEY", allow_env_fallback=False) is None
    )


def test_resolve_api_key_returns_none_without_env_var(fake_keyring: FakeKeyring) -> None:
    store = SecretStore(fake_keyring)
    assert resolve_api_key(store, "openrouter") is None
