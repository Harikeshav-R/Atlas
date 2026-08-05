"""Tests for the ``atlas company`` / ``atlas discover`` commands in :mod:`atlas.cli.main`.

Driven through the ``CliRunner`` with the database pointed at one shared in-memory
engine and a no-op logging setup. ``discover`` runs the real poll over a scripted
``FakeFetcher`` injected in place of the default HTTP fetcher, so no real network
is touched (AGENTS.md §6.2).
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest
from sqlmodel import SQLModel
from typer.testing import CliRunner

import atlas.cli.main as app_module
from atlas.cli.main import app
from atlas.db import create_db_engine, session_scope
from atlas.discovery.repository import get_or_create_ats_source
from atlas.scrape.fetcher import FetchResult
from atlas.scrape.repository import get_or_create_company, list_postings
from tests.conftest import FakeFetcher

if TYPE_CHECKING:
    from sqlalchemy.engine import Engine

runner = CliRunner()


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


_BOARD = json.dumps(
    {
        "jobs": [
            {
                "id": 1,
                "title": "Backend Engineer",
                "absolute_url": "https://boards.greenhouse.io/acme/jobs/1",
                "location": {"name": "Remote"},
                "content": "&lt;p&gt;Build.&lt;/p&gt;",
            }
        ],
        "meta": {"total": 1},
    }
)


# --- atlas company add ----------------------------------------------------------


def test_company_add_watchlists_greenhouse(shared_engine: Engine) -> None:
    result = runner.invoke(app, ["company", "add", "https://boards.greenhouse.io/acme"])
    assert result.exit_code == 0
    assert "Watchlisted" in result.output
    # The board is persisted and re-adding is a no-op.
    again = runner.invoke(app, ["company", "add", "https://boards.greenhouse.io/acme"])
    assert again.exit_code == 0
    assert "Already watchlisted" in again.output


def test_company_add_uses_name_override_and_json(shared_engine: Engine) -> None:
    result = runner.invoke(
        app,
        ["company", "add", "https://boards.greenhouse.io/acme", "--name", "Acme Inc", "--json"],
    )
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["name"] == "Acme Inc"
    assert payload["ats_type"] == "greenhouse"
    assert payload["board_token"] == "acme"
    assert payload["created"] is True


def test_company_add_rejects_unrecognized_url(shared_engine: Engine) -> None:
    result = runner.invoke(app, ["company", "add", "https://example.com/careers"])
    assert result.exit_code == 1
    assert "unrecognized ATS URL" in result.output
    assert "greenhouse" in result.output


# --- atlas company list ---------------------------------------------------------


def test_company_list_empty_and_populated(shared_engine: Engine) -> None:
    empty = runner.invoke(app, ["company", "list"])
    assert empty.exit_code == 0
    assert "atlas company add" in empty.output
    runner.invoke(app, ["company", "add", "https://boards.greenhouse.io/acme"])
    populated = runner.invoke(app, ["company", "list", "--json"])
    assert populated.exit_code == 0
    entries = json.loads(populated.output)["entries"]
    assert entries[0]["board_token"] == "acme"


# --- atlas discover -------------------------------------------------------------


def test_discover_polls_the_watchlist(
    shared_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    with session_scope(shared_engine) as session:
        company = get_or_create_company(session, name="Acme")
        assert company.id is not None
        get_or_create_ats_source(
            session, ats_type="greenhouse", board_token="acme", company_id=company.id
        )
    monkeypatch.setattr(
        app_module,
        "default_fetcher",
        FakeFetcher(
            FetchResult(url="x", status_code=200, content_type="application/json", body=_BOARD)
        ),
    )
    result = runner.invoke(app, ["discover"])
    assert result.exit_code == 0
    assert "Discovered" in result.output
    assert "atlas score" in result.output
    with session_scope(shared_engine) as session:
        assert [p.external_id for p in list_postings(session)] == ["1"]


def test_discover_empty_watchlist_json(
    shared_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    fetcher = FakeFetcher(
        FetchResult(url="x", status_code=200, content_type="application/json", body=_BOARD)
    )
    monkeypatch.setattr(app_module, "default_fetcher", fetcher)
    result = runner.invoke(app, ["discover", "--json"])
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload == {
        "sources_polled": 0,
        "discovered": 0,
        "skipped": 0,
        "failed_sources": 0,
    }
    assert fetcher.calls == []


def test_discover_text_no_new_postings_omits_hint(
    shared_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Empty watchlist → nothing discovered → the "atlas score" hint is not printed.
    fetcher = FakeFetcher(
        FetchResult(url="x", status_code=200, content_type="application/json", body=_BOARD)
    )
    monkeypatch.setattr(app_module, "default_fetcher", fetcher)
    result = runner.invoke(app, ["discover"])
    assert result.exit_code == 0
    assert "Discovered" in result.output
    assert "atlas score" not in result.output
