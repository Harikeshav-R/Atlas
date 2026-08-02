"""Alembic migration environment for Atlas.

Targets ``SQLModel.metadata`` (populated by importing :mod:`atlas.db.models`) so
autogenerate sees every table. The database URL comes from the Alembic config
when set — :func:`atlas.db.migrate.alembic_config` injects it in-process, and the
root ``alembic.ini`` sets it for the developer CLI — otherwise it falls back to
the real on-disk database (:func:`atlas.db.engine.db_path`), so a bare
``uv run alembic upgrade head`` migrates the user's database.

This module runs under Alembic (not pytest); it is excluded from coverage, mypy,
and ruff (see ``pyproject.toml``). The upgrade path is proven end-to-end by
``tests/test_db_migrate.py``.
"""

from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool
from sqlmodel import SQLModel

import atlas.db.models  # noqa: F401 - imported for its side effect: registers tables
from alembic import context
from atlas.db.engine import db_path, sqlite_url

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = SQLModel.metadata

# The ini placeholder that means "no real URL configured"; fall back to the app DB.
_INI_PLACEHOLDER = "driver://user:pass@localhost/dbname"


def _resolve_url() -> str:
    """Return the configured URL, or the app database when none is set."""
    configured = config.get_main_option("sqlalchemy.url")
    if not configured or configured == _INI_PLACEHOLDER:
        return sqlite_url(db_path())
    return configured


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode (emit SQL against a URL, no DBAPI)."""
    context.configure(
        url=_resolve_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode against a live connection."""
    section = config.get_section(config.config_ini_section, {})
    section["sqlalchemy.url"] = _resolve_url()
    connectable = engine_from_config(section, prefix="sqlalchemy.", poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
