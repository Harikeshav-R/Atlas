"""Transactional session scope for the Atlas data layer.

Callers mutate the database through :func:`session_scope`, a context manager that
opens a SQLModel :class:`~sqlmodel.Session`, **commits** on clean exit, **rolls
back** on any exception, and always **closes** the session. Keeping this the
single write path means transaction boundaries are consistent everywhere and no
half-applied write survives an error (PROJECT.md §4.1: short transactions).
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import TYPE_CHECKING

from sqlmodel import Session

if TYPE_CHECKING:
    from collections.abc import Iterator

    from sqlalchemy.engine import Engine

__all__ = ["session_scope"]


@contextmanager
def session_scope(engine: Engine) -> Iterator[Session]:
    """Yield a transactional :class:`~sqlmodel.Session` bound to ``engine``.

    Commits when the ``with`` block exits normally; rolls back and re-raises if
    it raises; closes the session in either case.

    Args:
        engine: The engine the session binds to (see
            :func:`atlas.db.engine.create_db_engine`).

    Yields:
        An open session; use it to add/query/delete within one transaction.
    """
    session = Session(engine)
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
