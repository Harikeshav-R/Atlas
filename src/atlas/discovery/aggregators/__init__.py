"""The aggregator adapter registry (PROJECT.md §5.4-B).

Holds the registered aggregator providers and the lookups the rest of discovery
uses. Two kinds of provider share one :class:`~atlas.discovery.aggregators.base.AggregatorAdapter`
interface:

- **Free feeds** (RemoteOK, Remotive) — no credentials, always active.
- **Key-gated** providers (Adzuna, USAJOBS) — built with credentials resolved from
  the OS keychain, inactive until a key is stored.

The registry maps each name to a **builder** ``(config, store) -> AggregatorAdapter
| None`` plus its ``requires_key`` flag. :func:`build_aggregator` is what the poll
calls: it returns the ready adapter, or ``None`` when a key-gated provider is
disabled / missing its key (an *inactive* source, not a failure). The pure name
lookups (:func:`validate_aggregator`, :func:`aggregator_requires_key`) let the CLI
validate a provider name without a :class:`~atlas.config.secrets.SecretStore`.

Adding a provider is a new adapter module plus one entry in :data:`_REGISTRY`; the
lookups derive from it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, NamedTuple

from atlas.discovery.aggregators.adzuna import build_adzuna
from atlas.discovery.aggregators.base import AggregatorAdapter
from atlas.discovery.aggregators.remoteok import RemoteOKAdapter
from atlas.discovery.aggregators.remotive import RemotiveAdapter
from atlas.discovery.aggregators.structure import SavedSearch
from atlas.discovery.aggregators.usajobs import build_usajobs
from atlas.discovery.errors import UnknownAggregatorError

if TYPE_CHECKING:
    from collections.abc import Callable

    from atlas.config.schema import AggregatorsConfig
    from atlas.config.secrets import SecretStore

__all__ = [
    "AGGREGATOR_TYPES",
    "AggregatorAdapter",
    "SavedSearch",
    "aggregator_requires_key",
    "build_aggregator",
    "validate_aggregator",
]


class _Provider(NamedTuple):
    """One registered aggregator provider.

    Attributes:
        requires_key: Whether the provider needs a credential (key-gated).
        build: Factory returning the built adapter, or ``None`` when it cannot be
            activated (a key-gated provider that is disabled / missing its key).
    """

    requires_key: bool
    build: Callable[[AggregatorsConfig, SecretStore], AggregatorAdapter | None]


#: Every registered aggregator provider, keyed by name.
_REGISTRY: dict[str, _Provider] = {
    "remoteok": _Provider(requires_key=False, build=lambda config, store: RemoteOKAdapter()),
    "remotive": _Provider(requires_key=False, build=lambda config, store: RemotiveAdapter()),
    "adzuna": _Provider(
        requires_key=True, build=lambda config, store: build_adzuna(config.adzuna, store)
    ),
    "usajobs": _Provider(
        requires_key=True, build=lambda config, store: build_usajobs(config.usajobs, store)
    ),
}

#: The registered provider names (sorted), for help text and error messages.
AGGREGATOR_TYPES: tuple[str, ...] = tuple(sorted(_REGISTRY))


def validate_aggregator(aggregator: str) -> None:
    """Raise :class:`UnknownAggregatorError` unless ``aggregator`` is registered.

    A pure name check with no config/keyring — the CLI uses it to reject an
    unknown provider before touching the database or the keychain.
    """
    if aggregator not in _REGISTRY:
        raise UnknownAggregatorError(aggregator, AGGREGATOR_TYPES)


def aggregator_requires_key(aggregator: str) -> bool:
    """Return whether ``aggregator`` is key-gated.

    Raises:
        UnknownAggregatorError: If no provider is registered under that name.
    """
    validate_aggregator(aggregator)
    return _REGISTRY[aggregator].requires_key


def build_aggregator(
    aggregator: str, *, config: AggregatorsConfig, store: SecretStore
) -> AggregatorAdapter | None:
    """Build the adapter for ``aggregator``, or ``None`` if it can't be activated.

    Free feeds always build. A key-gated provider builds only when enabled in
    ``config`` with its credential present in ``store``; otherwise this returns
    ``None`` (an inactive source the poll skips) rather than raising.

    Raises:
        UnknownAggregatorError: If no provider is registered under that name.
    """
    validate_aggregator(aggregator)
    return _REGISTRY[aggregator].build(config, store)
