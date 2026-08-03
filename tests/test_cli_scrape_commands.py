"""Tests for the ``atlas add`` and ``atlas postings`` commands in :mod:`atlas.cli.main`.

These drive the Typer commands through the ``CliRunner`` with every boundary
stubbed: an in-memory database engine, a no-op logging setup, and a stubbed
provider chain — and, for ``atlas add``, a stubbed :func:`atlas.scrape.service.add_posting`
so no real fetch or model call happens (its logic is covered in
``test_scrape_service``). The ``postings`` read commands run against seeded rows.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytest
from sqlmodel import SQLModel
from typer.testing import CliRunner

import atlas.cli.main as app_module
from atlas.cli.main import app
from atlas.config.errors import ConfigError
from atlas.config.schema import Config
from atlas.db import create_db_engine, session_scope
from atlas.scrape.errors import FetchError
from atlas.scrape.repository import (
    create_job_posting,
    get_or_create_company,
    get_or_create_url_source,
)
from atlas.scrape.service import AddOutcome

if TYPE_CHECKING:
    from sqlalchemy.engine import Engine

runner = CliRunner()

_FETCHED = datetime(2026, 8, 3, tzinfo=UTC)


@pytest.fixture(autouse=True)
def _stub_logging(monkeypatch: pytest.MonkeyPatch) -> None:
    """Stub the callback's logging setup so no test writes a real log file."""
    monkeypatch.setattr(app_module, "setup_logging", lambda **kwargs: 0)


@pytest.fixture
def shared_engine(monkeypatch: pytest.MonkeyPatch) -> Engine:
    """Point the commands at one shared in-memory engine with the schema created."""
    engine = create_db_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(engine, "dispose", lambda: None)
    monkeypatch.setattr(app_module, "initialize_database", lambda: engine)
    return engine


@pytest.fixture
def _stub_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    """Stub config/secret/provider resolution so ``atlas add`` builds no real chain."""
    monkeypatch.setattr(app_module, "load_config", lambda: Config())
    monkeypatch.setattr(app_module, "default_secret_store", lambda: object())
    monkeypatch.setattr(app_module, "build_provider_chain", lambda ai, store: object())


def _seed(engine: Engine, *, title: str = "Backend Engineer") -> int:
    with session_scope(engine) as session:
        company = get_or_create_company(session, name="Acme")
        source = get_or_create_url_source(session)
        assert company.id is not None
        assert source.id is not None
        posting = create_job_posting(
            session,
            source_id=source.id,
            company_id=company.id,
            title=title,
            apply_url="https://jobs.acme.test/1",
            dedupe_hash=title,
            fetched_at=_FETCHED,
            location="Remote",
            keywords=["python"],
            description="Build things.",
        )
        assert posting.id is not None
        return posting.id


# --- atlas add ------------------------------------------------------------------


def test_add_saves_posting(
    shared_engine: Engine, _stub_provider: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        app_module,
        "add_posting",
        lambda session, url, *, provider: AddOutcome(
            posting_id=1, created=True, title="Backend Engineer", company="Acme"
        ),
    )
    result = runner.invoke(app, ["add", "https://jobs.acme.test/1"])
    assert result.exit_code == 0
    assert "Saved posting" in result.output
    assert "Backend Engineer" in result.output


def test_add_noop_when_already_added(
    shared_engine: Engine, _stub_provider: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        app_module,
        "add_posting",
        lambda session, url, *, provider: AddOutcome(
            posting_id=5, created=False, title="Backend Engineer", company="Acme"
        ),
    )
    result = runner.invoke(app, ["add", "https://jobs.acme.test/1"])
    assert result.exit_code == 0
    assert "Already added" in result.output


def test_add_reports_scrape_error(
    shared_engine: Engine, _stub_provider: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(session: object, url: str, *, provider: object) -> AddOutcome:
        raise FetchError("could not fetch")

    monkeypatch.setattr(app_module, "add_posting", boom)
    result = runner.invoke(app, ["add", "https://jobs.acme.test/1"])
    assert result.exit_code == 1
    assert "atlas add" in result.output


def test_add_reports_config_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def bad_config() -> object:
        raise ConfigError("no config")

    monkeypatch.setattr(app_module, "load_config", bad_config)
    result = runner.invoke(app, ["add", "https://jobs.acme.test/1"])
    assert result.exit_code == 1
    assert "atlas add" in result.output


# --- atlas postings -------------------------------------------------------------


def test_postings_list_text_and_json(shared_engine: Engine) -> None:
    _seed(shared_engine)
    text = runner.invoke(app, ["postings", "list"])
    assert text.exit_code == 0
    assert "Job postings" in text.output
    listed = runner.invoke(app, ["postings", "list", "--json"])
    assert listed.exit_code == 0
    payload = json.loads(listed.output)
    assert [p["title"] for p in payload["postings"]] == ["Backend Engineer"]


def test_postings_list_empty(shared_engine: Engine) -> None:
    result = runner.invoke(app, ["postings", "list"])
    assert result.exit_code == 0
    assert "No postings yet" in result.output


def test_postings_show_text_and_json(shared_engine: Engine) -> None:
    posting_id = _seed(shared_engine)
    text = runner.invoke(app, ["postings", "show", str(posting_id)])
    assert text.exit_code == 0
    assert "Backend Engineer" in text.output
    shown = runner.invoke(app, ["postings", "show", str(posting_id), "--json"])
    assert shown.exit_code == 0
    payload = json.loads(shown.output)
    assert payload["title"] == "Backend Engineer"


def test_postings_show_missing_exits_one(shared_engine: Engine) -> None:
    result = runner.invoke(app, ["postings", "show", "999"])
    assert result.exit_code == 1
    assert "atlas postings show" in result.output
