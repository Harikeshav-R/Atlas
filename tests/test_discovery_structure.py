"""Tests for :mod:`atlas.discovery.structure` and :mod:`atlas.discovery.errors`."""

from __future__ import annotations

from atlas.discovery.errors import DiscoveryError, UnknownAtsError
from atlas.discovery.structure import DiscoveredPosting
from atlas.scrape.structure import ScrapedPosting


def test_discovered_posting_wraps_scraped_posting() -> None:
    posting = DiscoveredPosting(
        external_id="42",
        posting=ScrapedPosting(title="Backend Engineer", apply_url="https://x.test/42"),
    )
    assert posting.external_id == "42"
    assert posting.posting.title == "Backend Engineer"
    # Company is left empty — the poller supplies the watchlisted company.
    assert posting.posting.company == ""


def test_unknown_ats_error_is_a_discovery_error() -> None:
    err = UnknownAtsError("lever", ("greenhouse",))
    assert isinstance(err, DiscoveryError)
    assert err.supported == ("greenhouse",)
    assert "greenhouse" in str(err)


def test_unknown_ats_error_with_no_supported_providers() -> None:
    err = UnknownAtsError("lever", ())
    assert "none" in str(err)
