"""In-code filtering of aggregator postings against a saved search.

Aggregator feeds vary in what server-side filtering they support (RemoteOK's
public feed accepts no query at all; Remotive takes a ``search`` term but no
structured location/remote filter), so the shared, deterministic
:func:`matches_search` applies the :class:`~atlas.discovery.aggregators.structure.SavedSearch`
uniformly *after* normalization. Keeping it here (rather than in each adapter)
means every aggregator filters identically and the logic is unit-tested once.

Matching is case-insensitive and substring-based: the query terms are matched
against the posting's title / company / keywords / description, and the location
term against the posting's location. An empty query matches everything (the
adapter still returns the whole normalized feed).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from atlas.discovery.aggregators.structure import SavedSearch
    from atlas.scrape.structure import ScrapedPosting

__all__ = ["matches_search"]


def matches_search(posting: ScrapedPosting, spec: SavedSearch) -> bool:
    """Return whether ``posting`` satisfies the saved search ``spec``.

    A posting matches when **every** whitespace-separated query term appears
    (case-insensitively) somewhere in its searchable text (title, company,
    keywords, description); when a ``location`` filter is given, the posting's
    location must contain it; and when ``remote`` is set, the posting's
    ``remote_type`` must (``True``) or must not (``False``) be ``"remote"``.
    """
    haystack = " ".join(
        [
            posting.title,
            posting.company,
            " ".join(posting.keywords),
            posting.description,
        ]
    ).lower()
    for term in spec.query.lower().split():
        if term not in haystack:
            return False
    if spec.location is not None:
        location = (posting.location or "").lower()
        if spec.location.lower() not in location:
            return False
    if spec.remote is not None:
        is_remote = posting.remote_type == "remote"
        if is_remote != spec.remote:
            return False
    return True
