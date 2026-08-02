"""Programmatic Alembic driver for applying Atlas's schema migrations.

Atlas migrates its database in-process — on first launch and after upgrades —
rather than shelling out to the ``alembic`` CLI, so no ``alembic.ini`` needs to
ship with an installed copy (the root ``alembic.ini`` is a developer convenience
for ``uv run alembic …``). :func:`alembic_config` builds an Alembic
:class:`~alembic.config.Config` pointed at the migration scripts bundled inside
this package (``migrations/``, shipped in the wheel), and :func:`upgrade_to_head`
runs the upgrade, normalizing any failure to :class:`~atlas.db.errors.MigrationError`.
"""

from __future__ import annotations

import logging
from pathlib import Path

from alembic import command
from alembic.config import Config

from atlas.db.errors import MigrationError

__all__ = ["alembic_config", "upgrade_to_head"]

logger = logging.getLogger(__name__)

#: The migration environment bundled in this package (shipped in the wheel).
_MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"


def alembic_config(url: str) -> Config:
    """Build an Alembic :class:`~alembic.config.Config` for ``url``.

    Points ``script_location`` at this package's bundled ``migrations/`` and
    sets ``sqlalchemy.url`` to ``url`` so the same environment works for the real
    on-disk database and for a temporary test database alike.

    Args:
        url: The SQLAlchemy database URL to migrate.

    Returns:
        A configured :class:`~alembic.config.Config`.
    """
    config = Config()
    config.set_main_option("script_location", str(_MIGRATIONS_DIR))
    config.set_main_option("sqlalchemy.url", url)
    return config


def upgrade_to_head(url: str) -> None:
    """Upgrade the database at ``url`` to the latest schema revision.

    Args:
        url: The SQLAlchemy database URL to migrate.

    Raises:
        MigrationError: If the upgrade fails for any reason (the underlying
            Alembic/SQLAlchemy error is chained for daemon-side logging).
    """
    try:
        command.upgrade(alembic_config(url), "head")
    except Exception as exc:
        # Log the full traceback daemon-/CLI-side (no URL — it may embed a path),
        # then normalize every Alembic/SQLAlchemy failure to one Atlas type with
        # the original chained.
        logger.exception("Database migration to head failed.")
        raise MigrationError(f"Database migration to head failed for {url!r}.") from exc
