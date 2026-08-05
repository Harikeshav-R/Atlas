"""Tests for the aggregator registry in :mod:`atlas.discovery.aggregators`.

Pure lookups plus the credential-resolving builder — driven with a
:class:`FakeKeyring`, no fetcher, no DB.
"""

from __future__ import annotations

import pytest

from atlas.config.schema import AggregatorsConfig
from atlas.config.secrets import SecretStore
from atlas.discovery.aggregators import (
    AGGREGATOR_TYPES,
    aggregator_requires_key,
    build_aggregator,
    validate_aggregator,
)
from atlas.discovery.aggregators.adzuna import AdzunaAdapter
from atlas.discovery.aggregators.remoteok import RemoteOKAdapter
from atlas.discovery.errors import UnknownAggregatorError
from tests.conftest import FakeKeyring


def test_aggregator_types_are_sorted_names() -> None:
    assert AGGREGATOR_TYPES == ("adzuna", "remoteok", "remotive")


@pytest.mark.parametrize("name", ["adzuna", "remoteok", "remotive"])
def test_validate_aggregator_accepts_registered(name: str) -> None:
    validate_aggregator(name)  # does not raise


def test_validate_aggregator_unknown_raises() -> None:
    with pytest.raises(UnknownAggregatorError) as excinfo:
        validate_aggregator("linkedin")
    error = excinfo.value
    assert error.aggregator == "linkedin"
    assert error.supported == ("adzuna", "remoteok", "remotive")
    assert "Supported: adzuna, remoteok, remotive" in str(error)


@pytest.mark.parametrize(
    ("name", "requires_key"),
    [("remoteok", False), ("remotive", False), ("adzuna", True)],
)
def test_aggregator_requires_key(name: str, requires_key: bool) -> None:
    assert aggregator_requires_key(name) is requires_key


def test_aggregator_requires_key_unknown_raises() -> None:
    with pytest.raises(UnknownAggregatorError):
        aggregator_requires_key("linkedin")


def _config_store(fake_keyring: FakeKeyring) -> tuple[AggregatorsConfig, SecretStore]:
    return AggregatorsConfig(), SecretStore(fake_keyring)


def test_build_aggregator_free_provider_always_builds(fake_keyring: FakeKeyring) -> None:
    config, store = _config_store(fake_keyring)
    adapter = build_aggregator("remoteok", config=config, store=store)
    assert isinstance(adapter, RemoteOKAdapter)


def test_build_aggregator_key_gated_none_without_key(fake_keyring: FakeKeyring) -> None:
    # Default config has Adzuna disabled → None even with keys absent.
    config, store = _config_store(fake_keyring)
    assert build_aggregator("adzuna", config=config, store=store) is None


def test_build_aggregator_key_gated_builds_when_configured(fake_keyring: FakeKeyring) -> None:
    store = SecretStore(fake_keyring)
    store.set("adzuna_app_id", "id")
    store.set("adzuna_app_key", "key")
    config = AggregatorsConfig.model_validate({"adzuna": {"enabled": True}})
    adapter = build_aggregator("adzuna", config=config, store=store)
    assert isinstance(adapter, AdzunaAdapter)


def test_build_aggregator_unknown_raises(fake_keyring: FakeKeyring) -> None:
    config, store = _config_store(fake_keyring)
    with pytest.raises(UnknownAggregatorError):
        build_aggregator("linkedin", config=config, store=store)
