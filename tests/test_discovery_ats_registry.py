"""Tests for the ATS adapter registry in :mod:`atlas.discovery.ats`."""

from __future__ import annotations

import pytest

from atlas.discovery.ats import ATS_TYPES, detect_ats, get_adapter
from atlas.discovery.ats.greenhouse import GreenhouseAdapter
from atlas.discovery.ats.lever import LeverAdapter
from atlas.discovery.errors import UnknownAtsError


def test_ats_types_lists_registered_providers() -> None:
    assert ATS_TYPES == ("greenhouse", "lever")


def test_get_adapter_resolves_each_provider() -> None:
    assert isinstance(get_adapter("greenhouse"), GreenhouseAdapter)
    assert isinstance(get_adapter("lever"), LeverAdapter)


def test_get_adapter_unknown_raises() -> None:
    # smartrecruiters is a documented-but-unregistered provider (PROJECT.md §5.4-A).
    with pytest.raises(UnknownAtsError) as excinfo:
        get_adapter("smartrecruiters")
    assert excinfo.value.ats_type == "smartrecruiters"
    assert "greenhouse" in str(excinfo.value)


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://boards.greenhouse.io/acme", ("greenhouse", "acme")),
        ("https://jobs.lever.co/acme", ("lever", "acme")),
        ("https://api.lever.co/v0/postings/acme", ("lever", "acme")),
    ],
)
def test_detect_ats_classifies_urls(url: str, expected: tuple[str, str]) -> None:
    assert detect_ats(url) == expected


def test_detect_ats_returns_none_for_unrecognized_url() -> None:
    assert detect_ats("https://example.com/careers") is None
