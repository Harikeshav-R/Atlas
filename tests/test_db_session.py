"""Tests for the transactional scope in :mod:`atlas.db.session`."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from sqlmodel import Session, select

from atlas.db import User, session_scope

if TYPE_CHECKING:
    from sqlalchemy.engine import Engine


def test_scope_commits_on_clean_exit(db_engine: Engine) -> None:
    with session_scope(db_engine) as session:
        session.add(User(name="Sam"))
    # A fresh scope sees the committed row.
    with session_scope(db_engine) as session:
        assert session.exec(select(User)).one().name == "Sam"


def test_scope_rolls_back_and_reraises_on_error(db_engine: Engine) -> None:
    with pytest.raises(RuntimeError, match="boom"), session_scope(db_engine) as session:
        session.add(User(name="Ghost"))
        raise RuntimeError("boom")
    # The failed transaction left nothing behind.
    with session_scope(db_engine) as session:
        assert session.exec(select(User)).all() == []


def _spy_close(monkeypatch: pytest.MonkeyPatch) -> list[bool]:
    """Record each ``Session.close`` call, returning the recording list."""
    closed: list[bool] = []
    original = Session.close

    def tracking_close(self: Session) -> None:
        closed.append(True)
        original(self)

    monkeypatch.setattr("atlas.db.session.Session.close", tracking_close)
    return closed


def test_scope_closes_session_on_clean_exit(
    db_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    closed = _spy_close(monkeypatch)
    with session_scope(db_engine) as session:
        session.add(User(name="Sam"))
    assert closed == [True]


def test_scope_closes_session_on_error(db_engine: Engine, monkeypatch: pytest.MonkeyPatch) -> None:
    closed = _spy_close(monkeypatch)
    with pytest.raises(RuntimeError, match="fail"), session_scope(db_engine):
        raise RuntimeError("fail")
    assert closed == [True]
