"""Atlas data layer: SQLModel tables over SQLite (WAL) with Alembic migrations.

Atlas keeps all structured data in a single local SQLite database (PROJECT.md
§6), run in WAL mode for concurrent daemon-writer / TUI-reader access
(PROJECT.md §4.1). This package owns the engine and per-connection PRAGMAs
(:mod:`atlas.db.engine`), the transactional :func:`session_scope`
(:mod:`atlas.db.session`), the table models (:mod:`atlas.db.models`), and the
error hierarchy (:mod:`atlas.db.errors`). Large artifacts (PDFs, HTML snapshots)
live on disk; the database stores references, not blobs.
"""

from __future__ import annotations

from atlas.db.engine import create_db_engine, db_path, sqlite_url
from atlas.db.errors import DatabaseError, MigrationError
from atlas.db.migrate import alembic_config, initialize_database, upgrade_to_head
from atlas.db.models import (
    Application,
    Company,
    JobPosting,
    JobSource,
    MasterResume,
    MatchScore,
    Profile,
    ResumeBlock,
    TailoredResume,
    User,
)
from atlas.db.session import session_scope

__all__ = [
    "Application",
    "Company",
    "DatabaseError",
    "JobPosting",
    "JobSource",
    "MasterResume",
    "MatchScore",
    "MigrationError",
    "Profile",
    "ResumeBlock",
    "TailoredResume",
    "User",
    "alembic_config",
    "create_db_engine",
    "db_path",
    "initialize_database",
    "session_scope",
    "sqlite_url",
    "upgrade_to_head",
]
