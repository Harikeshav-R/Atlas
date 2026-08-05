"""The aggregator adapter registry (PROJECT.md §5.4-B).

Holds the tuple of registered
:class:`~atlas.discovery.aggregators.base.AggregatorAdapter` implementations and the
one lookup the rest of discovery uses:

- :func:`get_aggregator` — resolve an aggregator name (stored on a saved-search
  source) to its adapter, so the poll knows how to run a saved search.

Unlike the ATS registry there is **no ``detect`` walk**: an aggregator source is not
a pasted URL to classify — the user names the aggregator (``atlas source add
<aggregator> ...``), validated against :data:`AGGREGATOR_TYPES`.

Adding a provider is a new adapter module plus one entry in :data:`_AGGREGATOR_ADAPTERS`;
the lookup needs no change.
"""

from __future__ import annotations

from atlas.discovery.aggregators.base import AggregatorAdapter
from atlas.discovery.aggregators.remoteok import RemoteOKAdapter
from atlas.discovery.aggregators.remotive import RemotiveAdapter
from atlas.discovery.aggregators.structure import SavedSearch
from atlas.discovery.errors import UnknownAggregatorError

__all__ = [
    "AGGREGATOR_TYPES",
    "AggregatorAdapter",
    "SavedSearch",
    "get_aggregator",
]

#: Every registered aggregator adapter.
_AGGREGATOR_ADAPTERS: tuple[AggregatorAdapter, ...] = (
    RemoteOKAdapter(),
    RemotiveAdapter(),
)

#: The registered provider names (sorted), for help text and error messages.
AGGREGATOR_TYPES: tuple[str, ...] = tuple(
    sorted(adapter.aggregator_type for adapter in _AGGREGATOR_ADAPTERS)
)


def get_aggregator(aggregator: str) -> AggregatorAdapter:
    """Return the adapter registered for ``aggregator``.

    Raises:
        UnknownAggregatorError: If no adapter is registered under that name.
    """
    for adapter in _AGGREGATOR_ADAPTERS:
        if adapter.aggregator_type == aggregator:
            return adapter
    raise UnknownAggregatorError(aggregator, AGGREGATOR_TYPES)
