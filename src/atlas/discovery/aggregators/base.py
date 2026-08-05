"""The aggregator adapter interface (PROJECT.md §5.4-B).

The *second* discovery strategy, parallel to the per-company ATS boards
(:mod:`atlas.discovery.ats`). Where an ATS adapter watchlists one company's board
and pulls every job on it, an **aggregator adapter** runs a **saved keyword
search** (:class:`SavedSearch`) against a job feed/API and returns postings from
**many companies** — so, unlike an ATS posting, each discovered posting carries its
own :attr:`~atlas.scrape.structure.ScrapedPosting.company` (the poller cannot supply
one, and :func:`atlas.discovery.service.persist_aggregated` get-or-creates the
company per posting).

Every aggregator adapter (RemoteOK and Remotive today) implements the
:class:`AggregatorAdapter` Protocol. Following the house seam pattern
(:class:`~atlas.scrape.fetcher.Fetcher`, :class:`~atlas.discovery.ats.base.AtsAdapter`),
the adapter is a plain object with no I/O boundary of its own: it fetches through
the injected :class:`~atlas.scrape.fetcher.Fetcher`, so the hermetic suite drives it
with a :class:`FakeFetcher` and no real HTTP (AGENTS.md §6.2).

Unlike :class:`~atlas.discovery.ats.base.AtsAdapter`, there is **no ``detect(url)``
hook**: an aggregator source is not a pasted careers URL to classify — the user
names the aggregator and gives a query (``atlas source add <aggregator> --query
...``), so the registry (:mod:`atlas.discovery.aggregators`) resolves the adapter by
name only.

**Extension point (key-gated aggregators).** The free/no-key providers shipped here
need no credentials. Key-gated providers (Adzuna, USAJOBS — PROJECT.md §5.4-B) are a
fast-follow: they will resolve their key via
:func:`atlas.config.secrets.resolve_api_key` at construction and report unavailable
(rather than raise) when the key is absent. The interface stays minimal until then
so the free adapters carry no unused, untestable branches.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from atlas.discovery.aggregators.structure import SavedSearch
    from atlas.discovery.structure import DiscoveredPosting
    from atlas.scrape.fetcher import Fetcher

__all__ = ["AggregatorAdapter"]


@runtime_checkable
class AggregatorAdapter(Protocol):
    """A per-provider adapter for an aggregator keyword search.

    Implementations are registered in :mod:`atlas.discovery.aggregators`; a new
    provider is a new module plus one registry entry, with no change to this
    interface.
    """

    #: The provider's registry key, e.g. ``"remoteok"``. Also the value stored in
    #: the aggregator source's config.
    aggregator_type: str

    #: Whether the provider needs an API credential. Free feeds (RemoteOK,
    #: Remotive) set ``False`` and are always active; key-gated providers (Adzuna,
    #: USAJOBS) set ``True`` and are built with resolved credentials by
    #: :func:`atlas.discovery.aggregators.build_aggregator`, which returns ``None``
    #: (an inactive source) when the key is absent.
    requires_key: bool

    def search(
        self, spec: SavedSearch, *, fetcher: Fetcher, timeout_s: int
    ) -> list[DiscoveredPosting]:
        """Run ``spec`` against the aggregator and return the matching postings.

        Fetches the feed/API through the injected ``fetcher`` (never opens its own
        HTTP), then normalizes and filters each job to ``spec`` — populating each
        posting's ``company`` (an aggregator spans many companies).

        Args:
            spec: The saved search (query / location / filters) to run.
            fetcher: The injected HTTP boundary to fetch through.
            timeout_s: Per-request timeout in seconds.

        Returns:
            One :class:`~atlas.discovery.structure.DiscoveredPosting` per matching
            job (an empty list when the search has no results).

        Raises:
            DiscoveryError: If the aggregator response is unusable (non-JSON, or
                missing the expected listing).
            FetchError: If the aggregator cannot be fetched (propagated from the
                fetcher for the poll to catch).
        """
