"""Tests for the URL-open boundary in :mod:`atlas.platform.browser`.

The production :func:`atlas.platform.browser.default_url_opener` launches a real
browser and is ``# pragma: no cover``; the hermetic suite drives the open flow
through the injected :class:`~tests.conftest.FakeUrlOpener` instead. Here we cover
the protocol contract and the fake's recording/raising behaviour.
"""

from __future__ import annotations

import pytest

from atlas.platform.browser import UrlOpener, UrlOpenError
from tests.conftest import FakeUrlOpener


def test_fake_opener_satisfies_the_protocol() -> None:
    opener = FakeUrlOpener()
    assert isinstance(opener, UrlOpener)


def test_fake_opener_records_urls() -> None:
    opener = FakeUrlOpener()
    opener("https://jobs.acme.test/1")
    opener("https://jobs.acme.test/2")
    assert opener.opened == ["https://jobs.acme.test/1", "https://jobs.acme.test/2"]


def test_fake_opener_can_raise_url_open_error() -> None:
    opener = FakeUrlOpener(raises=UrlOpenError("boom"))
    with pytest.raises(UrlOpenError, match="boom"):
        opener("https://jobs.acme.test/1")
    # The URL is still recorded before raising.
    assert opener.opened == ["https://jobs.acme.test/1"]
