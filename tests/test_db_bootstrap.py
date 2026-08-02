"""Tests for the database bootstrap in :mod:`atlas.db.migrate`."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import inspect
from sqlmodel import select

import atlas.db.migrate as migrate_module
from atlas.db import MigrationError, Profile, initialize_database, session_scope, sqlite_url
from atlas.db.engine import create_db_engine


def test_initialize_database_migrates_and_returns_usable_engine(tmp_path: Path) -> None:
    url = sqlite_url(tmp_path / "atlas.db")
    engine = initialize_database(url)
    try:
        # Migrations ran: the schema (and Alembic bookkeeping) exists...
        tables = set(inspect(engine).get_table_names())
        assert {"user", "profile", "alembic_version"} <= tables
        # ...and the returned engine is usable for a real write/read.
        with session_scope(engine) as session:
            session.add(Profile(name="Backend Engineer"))
        with session_scope(engine) as session:
            stored = session.exec(select(Profile)).one()
            assert stored.name == "Backend Engineer"
    finally:
        # Dispose so tmp_path cleanup never trips the Windows file lock.
        engine.dispose()


def test_initialize_database_defaults_to_db_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # With no URL, the default path is used — pointed at tmp_path so the real
    # data dir is never touched (AGENTS.md §6.2).
    default_db = tmp_path / "default" / "atlas.db"
    monkeypatch.setattr(migrate_module, "db_path", lambda: default_db)
    engine = initialize_database()
    try:
        assert default_db.exists()
        assert "profile" in set(inspect(engine).get_table_names())
    finally:
        engine.dispose()


def test_initialize_database_is_idempotent(tmp_path: Path) -> None:
    url = sqlite_url(tmp_path / "atlas.db")
    first = initialize_database(url)
    first.dispose()
    # A second call against the already-current database is a harmless no-op.
    second = initialize_database(url)
    try:
        tables = set(inspect(second).get_table_names())
        assert {"user", "profile"} <= tables
    finally:
        second.dispose()


def test_initialize_database_disposes_engine_on_migration_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The engine builds, but the migration fails: the engine must be disposed
    # (no leaked connection/file lock) and the error propagated.
    disposed: list[bool] = []

    def _tracking_create(url: str | None = None):  # type: ignore[no-untyped-def]
        engine = create_db_engine(url)
        original_dispose = engine.dispose

        def _dispose(*args: object, **kwargs: object) -> None:
            disposed.append(True)
            original_dispose()

        monkeypatch.setattr(engine, "dispose", _dispose)
        return engine

    monkeypatch.setattr(migrate_module, "create_db_engine", _tracking_create)

    def _boom(url: str) -> None:
        raise MigrationError("boom")

    monkeypatch.setattr(migrate_module, "upgrade_to_head", _boom)

    with pytest.raises(MigrationError, match="boom"):
        initialize_database(sqlite_url(tmp_path / "atlas.db"))
    assert disposed == [True]
