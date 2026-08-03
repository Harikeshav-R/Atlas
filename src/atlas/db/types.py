"""Custom SQLAlchemy column types for Atlas's data layer.

SQLite has no native timezone-aware timestamp: a stored :class:`~datetime.datetime`
comes back **naive**, silently dropping its ``tzinfo``. Atlas works in UTC
internally, so :class:`UtcDateTime` normalizes every timestamp column at the
storage boundary — persisting UTC and re-attaching :data:`~datetime.UTC` on load —
so callers always get a timezone-aware UTC value back regardless of backend. Use
it for every timestamp column (PROJECT.md §6) rather than a bare
:class:`~sqlalchemy.types.DateTime`.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy.types import DateTime, TypeDecorator

if TYPE_CHECKING:
    from sqlalchemy.engine.interfaces import Dialect

__all__ = ["UtcDateTime"]


class UtcDateTime(TypeDecorator[datetime]):
    """A :class:`~datetime.datetime` column that stores and returns UTC.

    On write, a timezone-aware value is converted to UTC and a naive value is
    assumed to already be UTC; the value is stored without ``tzinfo`` (SQLite
    cannot hold it). On read, the stored value is returned with
    :data:`~datetime.UTC` attached, so the round-trip preserves an aware UTC
    timestamp.
    """

    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        """Normalize an inbound value to a naive UTC datetime for storage."""
        if value is None:
            return None
        if value.tzinfo is not None:
            value = value.astimezone(UTC)
        return value.replace(tzinfo=None)

    def process_result_value(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        """Re-attach :data:`~datetime.UTC` to a stored value on load."""
        if value is None:
            return None
        return value.replace(tzinfo=UTC)
