"""Error hierarchy for the Atlas data layer."""

from __future__ import annotations

__all__ = ["DatabaseError", "MigrationError"]


class DatabaseError(Exception):
    """Base class for every error raised by :mod:`atlas.db`."""


class MigrationError(DatabaseError):
    """Raised when an Alembic migration run fails.

    Wraps the underlying Alembic/SQLAlchemy error so callers catch a single
    Atlas type; the original exception is chained for daemon-side logging.
    """
