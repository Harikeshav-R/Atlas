"""Tests for the profile reporting/persistence logic in :mod:`atlas.cli.profile`."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from atlas.cli.console import console
from atlas.cli.profile import (
    ProfileListReport,
    ProfileSummary,
    apply_profile_edit,
    build_profile_report,
    load_profile_answers,
    persist_onboarding,
    persist_profile,
    render_profiles,
    switch_active_profile,
)
from atlas.db import session_scope
from atlas.profiles.errors import ProfileNotFoundError
from atlas.profiles.onboarding import OnboardingResult, ProfileAnswers, UserAnswers
from atlas.profiles.preferences import ProfilePreferences, Seniority
from atlas.profiles.repository import get_user

if TYPE_CHECKING:
    from sqlalchemy.engine import Engine


def _answers(name: str, role: str) -> ProfileAnswers:
    return ProfileAnswers(
        name=name,
        preferences=ProfilePreferences(target_roles=[role], seniority_levels=[Seniority.SENIOR]),
        tailoring_emphasis=["distributed systems"],
    )


def _rendered(report: ProfileListReport) -> str:
    with console.capture() as capture:
        console.print(render_profiles(report))
    return capture.get()


def test_persist_onboarding_creates_user_and_active_profile(db_engine: Engine) -> None:
    result = OnboardingResult(
        user=UserAnswers(name="Sam", email="sam@example.com"),
        profile=_answers("Backend Engineer", "Backend Engineer"),
    )
    with session_scope(db_engine) as session:
        profile_id = persist_onboarding(session, result)
    assert profile_id >= 1

    with session_scope(db_engine) as session:
        user = get_user(session)
        assert user is not None
        assert user.name == "Sam"
        report = build_profile_report(session)
    assert len(report.profiles) == 1
    summary = report.profiles[0]
    assert summary.name == "Backend Engineer"
    assert summary.active is True
    assert summary.target_roles == ["Backend Engineer"]
    assert summary.tailoring_emphasis == ["distributed systems"]


def test_persist_profile_inactive(db_engine: Engine) -> None:
    with session_scope(db_engine) as session:
        persist_profile(session, _answers("First", "A"), active=True)
    with session_scope(db_engine) as session:
        persist_profile(session, _answers("Second", "B"), active=False)
    with session_scope(db_engine) as session:
        report = build_profile_report(session)
    actives = [p.id for p in report.profiles if p.active]
    assert len(actives) == 1
    # The first profile stayed active because the second was added inactive.
    assert actives == [report.profiles[0].id]


def test_load_profile_answers_round_trips(db_engine: Engine) -> None:
    with session_scope(db_engine) as session:
        profile_id = persist_profile(session, _answers("Backend", "Backend Engineer"))
    with session_scope(db_engine) as session:
        loaded = load_profile_answers(session, profile_id)
    assert loaded.name == "Backend"
    assert loaded.preferences.target_roles == ["Backend Engineer"]
    assert loaded.tailoring_emphasis == ["distributed systems"]


def test_apply_profile_edit_updates_fields(db_engine: Engine) -> None:
    with session_scope(db_engine) as session:
        profile_id = persist_profile(session, _answers("Backend", "Backend Engineer"))
    with session_scope(db_engine) as session:
        apply_profile_edit(session, profile_id, _answers("Staff", "Staff Engineer"))
    with session_scope(db_engine) as session:
        loaded = load_profile_answers(session, profile_id)
    assert loaded.name == "Staff"
    assert loaded.preferences.target_roles == ["Staff Engineer"]


def test_switch_active_profile_changes_active(db_engine: Engine) -> None:
    with session_scope(db_engine) as session:
        first = persist_profile(session, _answers("First", "A"))
        persist_profile(session, _answers("Second", "B"))  # becomes active
    with session_scope(db_engine) as session:
        switch_active_profile(session, first)
    with session_scope(db_engine) as session:
        report = build_profile_report(session)
    actives = [p.id for p in report.profiles if p.active]
    assert actives == [first]


def test_load_profile_answers_missing_raises(db_engine: Engine) -> None:
    with (
        session_scope(db_engine) as session,
        pytest.raises(ProfileNotFoundError),
    ):
        load_profile_answers(session, 999)


def test_render_empty_report_hints_at_init() -> None:
    text = _rendered(ProfileListReport(profiles=[]))
    assert "atlas init" in text


def test_render_report_shows_profiles_and_active_mark() -> None:
    report = ProfileListReport(
        profiles=[
            ProfileSummary(
                id=1,
                name="Backend Engineer",
                active=True,
                target_roles=["Backend Engineer"],
                tailoring_emphasis=["distributed systems"],
            ),
            ProfileSummary(
                id=2,
                name="ML Engineer",
                active=False,
                target_roles=["ML Engineer"],
                tailoring_emphasis=[],
            ),
        ]
    )
    text = _rendered(report)
    assert "Profiles" in text
    assert "Backend Engineer" in text
    assert "ML Engineer" in text
    assert "active profile" in text


def test_report_json_round_trips() -> None:
    report = ProfileListReport(
        profiles=[
            ProfileSummary(
                id=1, name="X", active=True, target_roles=["r"], tailoring_emphasis=["e"]
            )
        ]
    )
    assert ProfileListReport.model_validate_json(report.model_dump_json()) == report
