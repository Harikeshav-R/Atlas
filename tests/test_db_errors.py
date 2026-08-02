"""Tests for the error hierarchy in :mod:`atlas.db.errors`."""

from __future__ import annotations

from atlas.db import DatabaseError, MigrationError


def test_migration_error_subclasses_database_error() -> None:
    assert issubclass(MigrationError, DatabaseError)


def test_database_error_subclasses_exception() -> None:
    assert issubclass(DatabaseError, Exception)


def test_migration_error_is_catchable_as_database_error() -> None:
    try:
        raise MigrationError("boom")
    except DatabaseError as exc:
        assert str(exc) == "boom"
