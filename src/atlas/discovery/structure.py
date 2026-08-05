"""Typed structure of a posting discovered from an ATS board (PROJECT.md §5.4).

A :class:`DiscoveredPosting` is what an ATS adapter
(:mod:`atlas.discovery.ats`) returns for each job on a board. Rather than invent a
second normalized-posting schema, it **reuses** the scraper's
:class:`~atlas.scrape.structure.ScrapedPosting` by composition and only adds the
one field discovery needs on top of it — the source's own stable id
(:attr:`external_id`), which becomes :attr:`atlas.db.models.JobPosting.external_id`
and the primary re-poll dedup key.

The company is *not* carried on the posting: an ATS board is polled for one
watchlisted company, so :attr:`ScrapedPosting.company` stays empty and the poller
supplies the company from the source instead (:mod:`atlas.discovery.service`).
"""

from __future__ import annotations

from pydantic import BaseModel

from atlas.scrape.structure import ScrapedPosting

__all__ = ["DiscoveredPosting"]


class DiscoveredPosting(BaseModel):
    """One posting discovered from an ATS board.

    Attributes:
        external_id: The ATS's own id for the posting, as a string. Stable across
            polls, so it is the primary key the poller dedups on within a source.
        posting: The normalized posting fields, reusing the scraper's shape
            (:class:`~atlas.scrape.structure.ScrapedPosting`). ``company`` is left
            empty — the poller supplies the watchlisted company.
    """

    external_id: str
    posting: ScrapedPosting
