"""Tests for the Alembic driver in :mod:`atlas.db.migrate`."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect

from atlas.db import MigrationError, sqlite_url
from atlas.db.migrate import alembic_config, upgrade_to_head


def test_alembic_config_sets_script_location_and_url() -> None:
    config = alembic_config("sqlite://")
    script_location = config.get_main_option("script_location")
    assert script_location is not None
    assert Path(script_location).name == "migrations"
    assert config.get_main_option("sqlalchemy.url") == "sqlite://"


def test_upgrade_to_head_creates_the_schema(tmp_path: Path) -> None:
    url = sqlite_url(tmp_path / "atlas.db")
    upgrade_to_head(url)
    engine = create_engine(url)
    try:
        tables = set(inspect(engine).get_table_names())
    finally:
        engine.dispose()
    # The migration built both tables plus Alembic's bookkeeping table.
    assert {"user", "profile", "alembic_version"} <= tables


def test_upgrade_to_head_wraps_failures_in_migration_error() -> None:
    # An unknown dialect can't be loaded, so Alembic raises during the run.
    with pytest.raises(MigrationError, match="migration to head failed"):
        upgrade_to_head("bogus://nope")
