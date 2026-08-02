"""Tests for the SQLModel tables in :mod:`atlas.db.models`."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlmodel import select

from atlas.db import Profile, User, session_scope

if TYPE_CHECKING:
    from sqlalchemy.engine import Engine


def test_user_defaults() -> None:
    user = User(name="Sam")
    assert user.id is None
    assert user.email is None
    assert user.settings == {}


def test_profile_defaults() -> None:
    profile = Profile(name="Backend Engineer")
    assert profile.id is None
    assert profile.preferences == {}
    assert profile.tailoring_emphasis == []
    assert profile.match_criteria == {}
    assert profile.active is True


def test_user_json_and_columns_round_trip(db_engine: Engine) -> None:
    with session_scope(db_engine) as session:
        session.add(User(name="Sam", email="sam@example.com", settings={"theme": "dark"}))
    # Read (and assert) inside a fresh scope, before its commit-at-exit expires
    # the instance and detaches it.
    with session_scope(db_engine) as session:
        stored = session.exec(select(User)).one()
        assert stored.id is not None
        assert stored.name == "Sam"
        assert stored.email == "sam@example.com"
        assert stored.settings == {"theme": "dark"}


def test_profile_json_columns_round_trip(db_engine: Engine) -> None:
    with session_scope(db_engine) as session:
        session.add(
            Profile(
                name="ML Engineer",
                preferences={"remote": True},
                tailoring_emphasis=["distributed systems", "product sense"],
                match_criteria={"min_salary": 150000},
                active=False,
            )
        )
    with session_scope(db_engine) as session:
        stored = session.exec(select(Profile)).one()
        assert stored.preferences == {"remote": True}
        assert stored.tailoring_emphasis == ["distributed systems", "product sense"]
        assert stored.match_criteria == {"min_salary": 150000}
        assert stored.active is False
