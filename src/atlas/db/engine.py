"""SQLite engine construction for Atlas's local data store.

Atlas stores structured data in a single local SQLite database (PROJECT.md §6)
run in **WAL** mode so the background daemon (the single writer for
discovery/scoring rows) and the TUI can access it concurrently without blocking
readers (PROJECT.md §4.1). This module builds the SQLAlchemy :class:`Engine` and
applies the required per-connection PRAGMAs.

The database URL is an **injectable boundary**: :func:`create_db_engine` defaults
to the real on-disk location (:func:`db_path`, under the platformdirs data dir)
but accepts any URL, so the hermetic test suite points it at an in-memory or
``tmp_path`` database and never touches a developer's real data (AGENTS.md §6.2).

**Disposal contract (cross-platform):** callers own the returned engine and must
:meth:`Engine.dispose` it when done. On Windows a still-open SQLite connection
holds a file lock on the ``.db`` and its ``-wal``/``-shm`` sidecars, so a
``tmp_path`` cannot be cleaned up until the engine is disposed — test fixtures
dispose in teardown for exactly this reason.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from sqlalchemy import create_engine, event, text
from sqlalchemy.pool import StaticPool

from atlas.config.paths import data_dir

if TYPE_CHECKING:
    from sqlalchemy.engine import Engine

__all__ = ["create_db_engine", "db_path", "sqlite_url"]

#: Name of the SQLite database file within the data dir.
_DB_FILENAME = "atlas.db"

#: The SQLAlchemy URLs that address an in-memory SQLite database. WAL is
#: meaningless for them and there is no file to lock, so parent-dir creation and
#: the Windows file-lock concern do not apply.
_MEMORY_URLS = frozenset({"sqlite://", "sqlite:///:memory:"})


def db_path() -> Path:
    """Return the path to Atlas's SQLite database inside the data dir.

    Pure — computes the path without creating anything (mirrors
    :func:`atlas.ai.probe_cache.probe_cache_file`). :func:`create_db_engine`
    creates the parent directory when it opens a file-backed database.
    """
    return data_dir() / _DB_FILENAME


def sqlite_url(path: Path) -> str:
    """Return the SQLAlchemy URL for a file-backed SQLite database at ``path``."""
    return f"sqlite:///{path}"


#: How long (milliseconds) a connection waits for a held write lock before
#: raising "database is locked". WAL keeps readers non-blocking, but the daemon
#: writer and a TUI-driven write can still briefly contend; a short busy timeout
#: lets the loser wait it out rather than fail (PROJECT.md §4.1, §17).
_BUSY_TIMEOUT_MS = 5000


def _enable_sqlite_pragmas(dbapi_connection: Any, _connection_record: Any) -> None:
    """Apply Atlas's per-connection SQLite PRAGMAs on every new connection.

    Enables **WAL** journaling (concurrent daemon writer + TUI readers,
    PROJECT.md §4.1), enforces **foreign keys** (off by default in SQLite), and
    sets a **busy timeout** so a connection waits briefly for a contended write
    lock instead of failing immediately. Runs for every pooled connection via
    SQLAlchemy's ``connect`` event. An in-memory database silently keeps its
    default journal mode, so this stays a single, always-executed path.
    """
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute(f"PRAGMA busy_timeout={_BUSY_TIMEOUT_MS}")
    finally:
        cursor.close()


def create_db_engine(url: str | None = None) -> Engine:
    """Build a SQLite :class:`Engine` with Atlas's WAL/foreign-key PRAGMAs.

    Args:
        url: The SQLAlchemy database URL. Defaults to the on-disk database at
            :func:`db_path`; pass ``"sqlite://"`` (in-memory) or a ``tmp_path``
            URL in tests. When the URL is file-backed, its parent directory is
            created if absent (the path helpers never create directories).

    Returns:
        A configured engine. The caller owns it and must
        :meth:`~sqlalchemy.engine.Engine.dispose` it when finished (see the
        module's cross-platform disposal contract).
    """
    resolved = url if url is not None else sqlite_url(db_path())
    is_memory = resolved in _MEMORY_URLS
    # ``check_same_thread=False`` lets the daemon scheduler and TUI share the
    # engine across threads (PROJECT.md §4.1); WAL keeps that concurrency safe.
    connect_args: dict[str, Any] = {"check_same_thread": False}
    if is_memory:
        # A default-pooled in-memory database gives each connection its own empty
        # schema; a single shared connection (StaticPool) makes the one in-memory
        # database persist across the engine's connections — needed for tests.
        engine = create_engine(resolved, connect_args=connect_args, poolclass=StaticPool)
    else:
        Path(resolved.removeprefix("sqlite:///")).parent.mkdir(parents=True, exist_ok=True)
        engine = create_engine(resolved, connect_args=connect_args)
    event.listen(engine, "connect", _enable_sqlite_pragmas)
    # Open one connection eagerly so the PRAGMAs are applied and a bad URL fails
    # here rather than lazily on first use.
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))
    return engine
