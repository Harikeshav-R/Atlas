"""Tests for on-disk snapshot storage in :mod:`atlas.scrape.snapshot`."""

from __future__ import annotations

from pathlib import Path

from atlas.scrape.snapshot import default_snapshots_dir, write_snapshot


def test_write_snapshot_creates_file_and_returns_ref(tmp_path: Path) -> None:
    ref = write_snapshot("<html>hi</html>", dedupe_hash="abc123", snapshots_dir=tmp_path)
    written = tmp_path / "abc123.html"
    assert Path(ref) == written
    assert written.read_text(encoding="utf-8") == "<html>hi</html>"


def test_write_snapshot_creates_missing_directory(tmp_path: Path) -> None:
    nested = tmp_path / "does" / "not" / "exist"
    ref = write_snapshot("<html/>", dedupe_hash="h", snapshots_dir=nested)
    assert Path(ref).exists()


def test_write_snapshot_overwrites_same_hash(tmp_path: Path) -> None:
    write_snapshot("first", dedupe_hash="h", snapshots_dir=tmp_path)
    write_snapshot("second", dedupe_hash="h", snapshots_dir=tmp_path)
    assert (tmp_path / "h.html").read_text(encoding="utf-8") == "second"


def test_default_snapshots_dir_under_data_dir() -> None:
    # Pure path composition — no directory is created by this helper.
    assert default_snapshots_dir().name == "snapshots"
