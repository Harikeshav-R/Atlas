"""Tests for the user/profile persistence in :mod:`atlas.profiles.repository`."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from sqlmodel import select

from atlas.db import session_scope
from atlas.db.models import User
from atlas.profiles.errors import ProfileNotFoundError
from atlas.profiles.preferences import ProfilePreferences, Seniority
from atlas.profiles.repository import (
    create_profile,
    get_active_profile,
    get_profile,
    get_user,
    list_profiles,
    set_active_profile,
    update_profile,
    upsert_user,
)

if TYPE_CHECKING:
    from sqlalchemy.engine import Engine

    from atlas.db.models import Profile


def _id(profile: Profile) -> int:
    """Return a flushed profile's id, narrowing ``int | None`` to ``int``."""
    assert profile.id is not None
    return profile.id


def test_get_user_none_when_empty(db_engine: Engine) -> None:
    with session_scope(db_engine) as session:
        assert get_user(session) is None


def test_upsert_user_creates_then_updates_single_row(db_engine: Engine) -> None:
    with session_scope(db_engine) as session:
        created = upsert_user(session, name="Sam", email="sam@example.com")
        # Capture the id inside the scope, before commit-at-exit expires it.
        created_id = created.id
        assert created_id is not None

    with session_scope(db_engine) as session:
        # A second upsert updates the same row rather than inserting a new one.
        updated = upsert_user(session, name="Samantha", email=None)
        assert updated.id == created_id

    with session_scope(db_engine) as session:
        users = list(session.exec(select(User)).all())
        assert len(users) == 1
        assert users[0].name == "Samantha"
        assert users[0].email is None
        assert users[0].id == created_id


def _prefs(role: str) -> ProfilePreferences:
    return ProfilePreferences(target_roles=[role], seniority_levels=[Seniority.SENIOR])


def test_create_profile_serializes_preferences_and_is_active(db_engine: Engine) -> None:
    with session_scope(db_engine) as session:
        profile = create_profile(
            session,
            name="Backend Engineer",
            preferences=_prefs("Backend Engineer"),
            tailoring_emphasis=["distributed systems"],
        )
        profile_id = _id(profile)

    with session_scope(db_engine) as session:
        stored = get_profile(session, profile_id)
        assert stored.active is True
        assert stored.tailoring_emphasis == ["distributed systems"]
        restored = ProfilePreferences.model_validate(stored.preferences)
        assert restored.target_roles == ["Backend Engineer"]
        assert restored.seniority_levels == [Seniority.SENIOR]


def test_create_profile_inactive_leaves_others_active(db_engine: Engine) -> None:
    with session_scope(db_engine) as session:
        first = create_profile(session, name="First", preferences=_prefs("A"))
        first_id = _id(first)
    with session_scope(db_engine) as session:
        create_profile(session, name="Second", preferences=_prefs("B"), active=False)
    with session_scope(db_engine) as session:
        active = get_active_profile(session)
        assert active is not None
        assert active.id == first_id


def test_create_active_profile_deactivates_previous(db_engine: Engine) -> None:
    with session_scope(db_engine) as session:
        create_profile(session, name="First", preferences=_prefs("A"))
    with session_scope(db_engine) as session:
        second = create_profile(session, name="Second", preferences=_prefs("B"))
        second_id = _id(second)
    with session_scope(db_engine) as session:
        actives = [p for p in list_profiles(session) if p.active]
        assert len(actives) == 1
        assert actives[0].id == second_id


def test_get_active_profile_none_when_empty(db_engine: Engine) -> None:
    with session_scope(db_engine) as session:
        assert get_active_profile(session) is None


def test_list_profiles_orders_by_creation(db_engine: Engine) -> None:
    with session_scope(db_engine) as session:
        create_profile(session, name="First", preferences=_prefs("A"))
        create_profile(session, name="Second", preferences=_prefs("B"))
    with session_scope(db_engine) as session:
        names = [p.name for p in list_profiles(session)]
        assert names == ["First", "Second"]


def test_update_profile_changes_only_given_fields(db_engine: Engine) -> None:
    with session_scope(db_engine) as session:
        profile = create_profile(
            session,
            name="Backend",
            preferences=_prefs("Backend Engineer"),
            tailoring_emphasis=["a"],
        )
        profile_id = _id(profile)

    with session_scope(db_engine) as session:
        # Only the name changes; preferences and emphasis are preserved.
        update_profile(session, profile_id, name="Backend v2")
    with session_scope(db_engine) as session:
        stored = get_profile(session, profile_id)
        assert stored.name == "Backend v2"
        assert stored.tailoring_emphasis == ["a"]
        assert ProfilePreferences.model_validate(stored.preferences).target_roles == [
            "Backend Engineer"
        ]

    with session_scope(db_engine) as session:
        update_profile(
            session,
            profile_id,
            preferences=_prefs("Staff Engineer"),
            tailoring_emphasis=["b", "c"],
        )
    with session_scope(db_engine) as session:
        stored = get_profile(session, profile_id)
        assert stored.name == "Backend v2"
        assert stored.tailoring_emphasis == ["b", "c"]
        assert ProfilePreferences.model_validate(stored.preferences).target_roles == [
            "Staff Engineer"
        ]


def test_set_active_profile_switches_the_active_one(db_engine: Engine) -> None:
    with session_scope(db_engine) as session:
        first = create_profile(session, name="First", preferences=_prefs("A"))
        second = create_profile(session, name="Second", preferences=_prefs("B"))
        first_id, second_id = _id(first), _id(second)
    # Second is active after creation; switch back to first.
    with session_scope(db_engine) as session:
        set_active_profile(session, first_id)
    with session_scope(db_engine) as session:
        actives = [p.id for p in list_profiles(session) if p.active]
        assert actives == [first_id]
        assert second_id not in actives


def test_get_profile_missing_raises(db_engine: Engine) -> None:
    with (
        session_scope(db_engine) as session,
        pytest.raises(ProfileNotFoundError, match="999"),
    ):
        get_profile(session, 999)


def test_update_profile_missing_raises(db_engine: Engine) -> None:
    with (
        session_scope(db_engine) as session,
        pytest.raises(ProfileNotFoundError),
    ):
        update_profile(session, 999, name="nope")


def test_set_active_profile_missing_raises(db_engine: Engine) -> None:
    with (
        session_scope(db_engine) as session,
        pytest.raises(ProfileNotFoundError),
    ):
        set_active_profile(session, 999)
