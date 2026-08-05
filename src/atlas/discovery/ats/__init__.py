"""The ATS adapter registry (PROJECT.md §5.4-A).

Holds the tuple of registered :class:`~atlas.discovery.ats.base.AtsAdapter`
implementations and the two lookups the rest of discovery uses:

- :func:`get_adapter` — resolve an ``ats_type`` string (stored on a watchlisted
  company / ATS source) to its adapter, so the poll knows how to fetch a board.
- :func:`detect_ats` — walk the adapters' pure ``detect`` hooks to classify a
  pasted careers URL into ``(ats_type, board_token)``, so ``atlas company add
  <url>`` needs no ``--ats`` flag.

Adding a provider is a new adapter module plus one entry in :data:`_ADAPTERS`; the
lookups need no change.
"""

from __future__ import annotations

from atlas.discovery.ats.ashby import AshbyAdapter
from atlas.discovery.ats.base import AtsAdapter
from atlas.discovery.ats.greenhouse import GreenhouseAdapter
from atlas.discovery.ats.lever import LeverAdapter
from atlas.discovery.ats.workday import WorkdayAdapter
from atlas.discovery.errors import UnknownAtsError

__all__ = ["ATS_TYPES", "AtsAdapter", "detect_ats", "get_adapter"]

#: Every registered ATS adapter, tried in order by :func:`detect_ats`.
_ADAPTERS: tuple[AtsAdapter, ...] = (
    GreenhouseAdapter(),
    LeverAdapter(),
    AshbyAdapter(),
    WorkdayAdapter(),
)

#: The registered provider names (sorted), for help text and error messages.
ATS_TYPES: tuple[str, ...] = tuple(sorted(adapter.ats_type for adapter in _ADAPTERS))


def get_adapter(ats_type: str) -> AtsAdapter:
    """Return the adapter registered for ``ats_type``.

    Raises:
        UnknownAtsError: If no adapter is registered under that name.
    """
    for adapter in _ADAPTERS:
        if adapter.ats_type == ats_type:
            return adapter
    raise UnknownAtsError(ats_type, ATS_TYPES)


def detect_ats(url: str) -> tuple[str, str] | None:
    """Classify ``url`` into ``(ats_type, board_token)``, or ``None``.

    Returns the first registered adapter whose :meth:`~AtsAdapter.detect` matches
    ``url`` (pure, offline URL matching), or ``None`` when no adapter recognizes
    it (the caller reports an unsupported URL).
    """
    for adapter in _ADAPTERS:
        token = adapter.detect(url)
        if token is not None:
            return adapter.ats_type, token
    return None
