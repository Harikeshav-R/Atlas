"""Tests for the Alembic driver in :mod:`atlas.db.migrate`."""

from __future__ import annotations

import logging
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
    # The migrations build every table declared so far plus Alembic's bookkeeping.
    assert {
        "user",
        "profile",
        "master_resume",
        "resume_block",
        "company",
        "job_source",
        "job_posting",
        "match_score",
        "application",
        "tailored_resume",
        "alembic_version",
    } <= tables


def test_upgrade_to_head_wraps_failures_in_migration_error(
    caplog: pytest.LogCaptureFixture,
) -> None:
    # An unknown dialect can't be loaded, so Alembic raises during the run.
    with (
        caplog.at_level(logging.ERROR, logger="atlas.db.migrate"),
        pytest.raises(MigrationError, match="migration to head failed"),
    ):
        upgrade_to_head("bogus://nope")
    # The failure is logged daemon-/CLI-side (without the URL) before re-raising.
    assert any(
        record.levelno == logging.ERROR and "migration to head failed" in record.message.lower()
        for record in caplog.records
    )
