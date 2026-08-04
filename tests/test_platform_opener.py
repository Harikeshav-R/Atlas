"""Tests for the file-open boundary in :mod:`atlas.platform.opener`.

The production :func:`atlas.platform.opener.default_file_opener` launches a real
GUI application and is ``# pragma: no cover``; the hermetic suite drives the open
flow through the injected :class:`~tests.conftest.FakeFileOpener` instead. Here we
cover the protocol contract and the fake's recording/raising behaviour.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from atlas.platform.opener import FileOpener, FileOpenError
from tests.conftest import FakeFileOpener


def test_fake_opener_satisfies_the_protocol() -> None:
    opener = FakeFileOpener()
    assert isinstance(opener, FileOpener)


def test_fake_opener_records_paths() -> None:
    opener = FakeFileOpener()
    opener(Path("/data/renders/a.pdf"))
    opener(Path("/data/renders/b.pdf"))
    assert opener.opened == [Path("/data/renders/a.pdf"), Path("/data/renders/b.pdf")]


def test_fake_opener_can_raise_file_open_error() -> None:
    opener = FakeFileOpener(raises=FileOpenError("boom"))
    with pytest.raises(FileOpenError, match="boom"):
        opener(Path("/data/renders/a.pdf"))
    # The path is still recorded before raising.
    assert opener.opened == [Path("/data/renders/a.pdf")]
