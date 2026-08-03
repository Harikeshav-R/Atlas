"""Tests for the on-disk PDF store in :mod:`atlas.render.store`."""

from __future__ import annotations

from typing import TYPE_CHECKING

from atlas.render.store import default_renders_dir, write_pdf

if TYPE_CHECKING:
    from pathlib import Path


def test_default_renders_dir_under_data_dir() -> None:
    # Composed under the platformdirs data dir; the helper is pure (no mkdir).
    assert default_renders_dir().name == "renders"


def test_write_pdf_creates_dir_and_writes_bytes(tmp_path: Path) -> None:
    renders_dir = tmp_path / "renders"  # does not exist yet
    path = write_pdf(b"%PDF-1", filename="sam__resume__v1.pdf", renders_dir=renders_dir)
    written = renders_dir / "sam__resume__v1.pdf"
    assert path == str(written)
    assert written.read_bytes() == b"%PDF-1"


def test_write_pdf_overwrites_same_filename(tmp_path: Path) -> None:
    write_pdf(b"first", filename="r.pdf", renders_dir=tmp_path)
    write_pdf(b"second", filename="r.pdf", renders_dir=tmp_path)
    assert (tmp_path / "r.pdf").read_bytes() == b"second"
