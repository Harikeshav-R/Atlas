"""The saved-search spec an aggregator adapter runs (PROJECT.md §5.4-B).

A :class:`SavedSearch` is the per-profile "keywords + location + filters" a user
defines with ``atlas source add <aggregator> --query ...``. It is what serializes
into an aggregator :class:`~atlas.db.models.JobSource`'s ``config`` JSON (under the
``search`` key) and what :meth:`~atlas.discovery.aggregators.base.AggregatorAdapter.search`
receives when the poll rebuilds the source.

Like :class:`~atlas.scrape.structure.ScrapedPosting`, the base ignores unknown keys
so a source persisted by an older/newer schema still rebuilds (its now-unknown keys
are dropped rather than rejected).
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

__all__ = ["SavedSearch"]


class SavedSearch(BaseModel):
    """A saved keyword search run against an aggregator (PROJECT.md §5.4-B).

    Attributes:
        query: The keywords to search for (e.g. ``"python backend"``).
        location: A location filter, if any (matched against the posting's
            location as free text).
        remote: Whether to keep only remote roles (``True``), only non-remote
            (``False``), or not filter on remoteness (``None``, the default).
    """

    model_config = ConfigDict(extra="ignore")

    query: str
    location: str | None = None
    remote: bool | None = None
