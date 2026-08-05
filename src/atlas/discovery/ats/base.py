"""The ATS adapter interface (PROJECT.md §5.4-A).

Every per-provider ATS adapter (Greenhouse today; Lever/Ashby/Workday as
fast-follow PRs) implements the :class:`AtsAdapter` Protocol. Following the house
seam pattern (:class:`~atlas.scrape.fetcher.Fetcher`,
:class:`~atlas.daemon.scheduler.Scheduler`), the adapter is a plain object with no
I/O boundary of its own: it fetches through the injected
:class:`~atlas.scrape.fetcher.Fetcher`, so the hermetic suite drives it with a
:class:`FakeFetcher` and no real HTTP (AGENTS.md §6.2).

Two responsibilities:

- :meth:`AtsAdapter.detect` — a **pure, offline** URL classifier: given a
  careers/board URL, return the board token if this ATS owns the URL, else
  ``None``. The registry (:mod:`atlas.discovery.ats`) walks the adapters with this
  so ``atlas company add <url>`` needs no ``--ats`` flag.
- :meth:`AtsAdapter.list_postings` — fetch the board's public listing and
  normalize each job into a :class:`~atlas.discovery.structure.DiscoveredPosting`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from atlas.discovery.structure import DiscoveredPosting
    from atlas.scrape.fetcher import Fetcher

__all__ = ["AtsAdapter"]


@runtime_checkable
class AtsAdapter(Protocol):
    """A per-provider adapter for a structured ATS job board.

    Implementations are registered in :mod:`atlas.discovery.ats`; a new provider
    is a new module plus one registry entry, with no change to this interface.
    """

    #: The provider's registry key, e.g. ``"greenhouse"``. Also the value stored
    #: in :attr:`atlas.db.models.Company.ats_type` and the ATS source's config.
    ats_type: str

    def detect(self, url: str) -> str | None:
        """Return the board token if this ATS owns ``url``, else ``None``.

        Pure and offline — matches on the URL's host/path/query only, never
        fetching. Used by the registry's ``detect_ats`` to resolve a pasted
        careers URL to ``(ats_type, board_token)``.
        """

    def list_postings(
        self, board_ref: str, *, fetcher: Fetcher, timeout_s: int
    ) -> list[DiscoveredPosting]:
        """Fetch and normalize every posting on the board ``board_ref``.

        Args:
            board_ref: The board token/reference identifying the company's board.
            fetcher: The injected HTTP boundary to fetch the board through.
            timeout_s: Per-request timeout in seconds.

        Returns:
            One :class:`~atlas.discovery.structure.DiscoveredPosting` per job
            (an empty list when the board has none).

        Raises:
            DiscoveryError: If the board response is unusable (non-JSON, or missing
                the expected listing).
            FetchError: If the board cannot be fetched (propagated from the
                fetcher for the poll to catch).
        """
