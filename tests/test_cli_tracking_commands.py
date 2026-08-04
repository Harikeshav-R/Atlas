"""Tests for the ``atlas apply``, ``atlas status``, and ``atlas list`` commands.

These drive the Typer commands through the ``CliRunner`` with the database pointed
at one shared in-memory engine and logging stubbed. The tracking commands are
deterministic (no AI), so no provider/config chain is stubbed.
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
from atlas.db import create_db_engine, session_scope
from atlas.profiles.preferences import ProfilePreferences
from atlas.profiles.repository import create_profile
from atlas.scrape.repository import (
    create_job_posting,
    get_or_create_company,
    get_or_create_url_source,
)
from atlas.tailor.repository import get_or_create_application

if TYPE_CHECKING:
    from sqlalchemy.engine import Engine

runner = CliRunner()

_NOW = datetime(2026, 8, 4, 9, 30, tzinfo=UTC)


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
            apply_url=f"https://jobs.acme.test/{title}",
            dedupe_hash=title,
            fetched_at=_NOW,
        )
        profile = create_profile(session, name="BE", preferences=ProfilePreferences(), active=True)
        assert posting.id is not None
        assert profile.id is not None
        application = get_or_create_application(
            session, job_posting_id=posting.id, profile_id=profile.id, clock=_NOW
        )
        assert application.id is not None
        return application.id


# --- atlas status set -----------------------------------------------------------


def test_status_set_text_and_json(shared_engine: Engine) -> None:
    app_id = _seed(shared_engine)
    text = runner.invoke(app, ["status", "set", str(app_id), "ready"])
    assert text.exit_code == 0
    assert "ready" in text.output
    shown = runner.invoke(app, ["status", "set", str(app_id), "applied", "--json"])
    assert shown.exit_code == 0
    payload = json.loads(shown.output)
    assert payload["new_status"] == "applied"
    assert payload["applied_at"] is not None


def test_status_set_records_due(shared_engine: Engine) -> None:
    app_id = _seed(shared_engine)
    runner.invoke(app, ["status", "set", str(app_id), "ready"])
    result = runner.invoke(
        app, ["status", "set", str(app_id), "applied", "--due", "2026-08-15", "--json"]
    )
    assert result.exit_code == 0
    assert json.loads(result.output)["due"] == "2026-08-15T00:00:00"


def test_status_set_invalid_exits_one(shared_engine: Engine) -> None:
    app_id = _seed(shared_engine)
    result = runner.invoke(app, ["status", "set", str(app_id), "offer"])
    assert result.exit_code == 1
    assert "atlas status set" in result.output


def test_status_set_force_overrides(shared_engine: Engine) -> None:
    app_id = _seed(shared_engine)
    result = runner.invoke(app, ["status", "set", str(app_id), "offer", "--force"])
    assert result.exit_code == 0
    assert "offer" in result.output


def test_status_set_unknown_exits_one(shared_engine: Engine) -> None:
    result = runner.invoke(app, ["status", "set", "999", "ready"])
    assert result.exit_code == 1
    assert "atlas status set" in result.output


# --- atlas apply mark -----------------------------------------------------------


def test_apply_mark_text_and_json(shared_engine: Engine) -> None:
    app_id = _seed(shared_engine)
    runner.invoke(app, ["status", "set", str(app_id), "ready"])
    text = runner.invoke(app, ["apply", "mark", str(app_id)])
    assert text.exit_code == 0
    assert "applied" in text.output
    # A second mark from a terminal-ish state is blocked without --force.
    runner.invoke(app, ["status", "set", str(app_id), "offer", "--json"])
    forced = runner.invoke(app, ["apply", "mark", str(app_id), "--force", "--json"])
    assert forced.exit_code == 0
    assert json.loads(forced.output)["new_status"] == "applied"


def test_apply_mark_invalid_exits_one(shared_engine: Engine) -> None:
    app_id = _seed(shared_engine)  # status is "preparing" — can't jump to applied
    result = runner.invoke(app, ["apply", "mark", str(app_id)])
    assert result.exit_code == 1
    assert "atlas apply mark" in result.output


def test_apply_mark_unknown_exits_one(shared_engine: Engine) -> None:
    result = runner.invoke(app, ["apply", "mark", "999"])
    assert result.exit_code == 1
    assert "atlas apply mark" in result.output


# --- atlas list -----------------------------------------------------------------


def test_list_text_and_json(shared_engine: Engine) -> None:
    _seed(shared_engine)
    text = runner.invoke(app, ["list"])
    assert text.exit_code == 0
    assert "Applications" in text.output
    listed = runner.invoke(app, ["list", "--json"])
    assert listed.exit_code == 0
    payload = json.loads(listed.output)
    assert [a["title"] for a in payload["applications"]] == ["Backend Engineer"]


def test_list_empty(shared_engine: Engine) -> None:
    result = runner.invoke(app, ["list"])
    assert result.exit_code == 0
    assert "No applications yet" in result.output


def test_list_filters_by_status_and_profile(shared_engine: Engine) -> None:
    app_id = _seed(shared_engine)
    runner.invoke(app, ["status", "set", str(app_id), "ready"])
    ready = runner.invoke(app, ["list", "--status", "ready", "--json"])
    assert ready.exit_code == 0
    assert len(json.loads(ready.output)["applications"]) == 1
    preparing = runner.invoke(app, ["list", "--status", "preparing", "--json"])
    assert json.loads(preparing.output)["applications"] == []
    by_profile = runner.invoke(app, ["list", "--profile", "1", "--json"])
    assert len(json.loads(by_profile.output)["applications"]) == 1
