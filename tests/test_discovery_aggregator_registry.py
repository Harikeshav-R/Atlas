"""Tests for the aggregator registry in :mod:`atlas.discovery.aggregators`.

Pure lookups over the registered adapters — no fetcher, no DB.
"""

from __future__ import annotations

import pytest

from atlas.discovery.aggregators import AGGREGATOR_TYPES, get_aggregator
from atlas.discovery.aggregators.remoteok import RemoteOKAdapter
from atlas.discovery.aggregators.remotive import RemotiveAdapter
from atlas.discovery.errors import UnknownAggregatorError


def test_aggregator_types_are_sorted_names() -> None:
    assert AGGREGATOR_TYPES == ("remoteok", "remotive")


@pytest.mark.parametrize(
    ("name", "cls"),
    [("remoteok", RemoteOKAdapter), ("remotive", RemotiveAdapter)],
)
def test_get_aggregator_resolves_each_provider(name: str, cls: type) -> None:
    adapter = get_aggregator(name)
    assert isinstance(adapter, cls)
    assert adapter.aggregator_type == name


def test_get_aggregator_unknown_raises() -> None:
    with pytest.raises(UnknownAggregatorError) as excinfo:
        get_aggregator("linkedin")
    error = excinfo.value
    assert error.aggregator == "linkedin"
    assert error.supported == ("remoteok", "remotive")
    assert "Supported: remoteok, remotive" in str(error)
