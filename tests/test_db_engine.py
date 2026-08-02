"""Tests for SQLite engine construction in :mod:`atlas.db.engine`."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlmodel import text

from atlas.db.engine import create_db_engine, db_path, sqlite_url


def test_db_path_lives_under_data_dir(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("atlas.db.engine.data_dir", lambda: Path("/fake/data"))
    assert db_path() == Path("/fake/data/atlas.db")


def test_sqlite_url_formats_a_file_url() -> None:
    # The URL is the SQLite prefix plus the path rendered for the current OS
    # (backslashes on Windows), so compare against the platform path, not a
    # hardcoded POSIX form.
    path = Path("/fake/data/atlas.db")
    url = sqlite_url(path)
    assert url.startswith("sqlite:///")
    assert url.removeprefix("sqlite:///") == str(path)


def test_default_url_uses_db_path(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    # No URL argument → the engine opens the database at db_path().
    monkeypatch.setattr("atlas.db.engine.data_dir", lambda: tmp_path)
    engine = create_db_engine()
    try:
        assert (tmp_path / "atlas.db").exists()
    finally:
        engine.dispose()


def test_file_engine_enables_wal_and_foreign_keys(tmp_path: Path) -> None:
    engine = create_db_engine(sqlite_url(tmp_path / "atlas.db"))
    try:
        with engine.connect() as connection:
            journal_mode = connection.execute(text("PRAGMA journal_mode")).scalar_one()
            foreign_keys = connection.execute(text("PRAGMA foreign_keys")).scalar_one()
        assert journal_mode == "wal"
        assert foreign_keys == 1
    finally:
        engine.dispose()


def test_file_engine_creates_missing_parent_directory(tmp_path: Path) -> None:
    nested = tmp_path / "does" / "not" / "exist" / "atlas.db"
    engine = create_db_engine(sqlite_url(nested))
    try:
        assert nested.parent.is_dir()
        assert nested.exists()
    finally:
        engine.dispose()


@pytest.mark.parametrize("url", ["sqlite://", "sqlite:///:memory:"])
def test_memory_engine_connects_without_a_file(url: str) -> None:
    # In-memory URLs skip parent-dir creation and still enforce foreign keys.
    engine = create_db_engine(url)
    try:
        with engine.connect() as connection:
            assert connection.execute(text("PRAGMA foreign_keys")).scalar_one() == 1
    finally:
        engine.dispose()
