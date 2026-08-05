"""Tests for the ATS adapter registry in :mod:`atlas.discovery.ats`."""

from __future__ import annotations

import pytest

from atlas.discovery.ats import ATS_TYPES, detect_ats, get_adapter
from atlas.discovery.ats.greenhouse import GreenhouseAdapter
from atlas.discovery.errors import UnknownAtsError


def test_ats_types_lists_greenhouse() -> None:
    assert ATS_TYPES == ("greenhouse",)


def test_get_adapter_resolves_greenhouse() -> None:
    assert isinstance(get_adapter("greenhouse"), GreenhouseAdapter)


def test_get_adapter_unknown_raises() -> None:
    with pytest.raises(UnknownAtsError) as excinfo:
        get_adapter("lever")
    assert excinfo.value.ats_type == "lever"
    assert "greenhouse" in str(excinfo.value)


def test_detect_ats_classifies_greenhouse_url() -> None:
    assert detect_ats("https://boards.greenhouse.io/acme") == ("greenhouse", "acme")


def test_detect_ats_returns_none_for_unrecognized_url() -> None:
    assert detect_ats("https://example.com/careers") is None
