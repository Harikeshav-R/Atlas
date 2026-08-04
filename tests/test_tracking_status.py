"""Tests for the pure application status state machine in :mod:`atlas.tracking.status`."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from atlas.tracking.status import (
    ALLOWED_TRANSITIONS,
    TERMINAL_STATUSES,
    ApplicationStatus,
    StatusTransition,
    can_transition,
)

_NOW = datetime(2026, 8, 4, 9, 30, tzinfo=UTC)


def test_every_status_has_a_transition_entry() -> None:
    """The transition graph is total — every status is a key."""
    assert set(ALLOWED_TRANSITIONS) == set(ApplicationStatus)


def test_terminal_statuses_have_no_outgoing_edges() -> None:
    """A terminal stage cannot be left without ``--force`` (empty edge set)."""
    for status in TERMINAL_STATUSES:
        assert ALLOWED_TRANSITIONS[status] == frozenset()


@pytest.mark.parametrize(
    ("current", "target"),
    [
        (ApplicationStatus.SAVED, ApplicationStatus.PREPARING),
        (ApplicationStatus.PREPARING, ApplicationStatus.READY),
        (ApplicationStatus.READY, ApplicationStatus.APPLIED),
        (ApplicationStatus.APPLIED, ApplicationStatus.OA),
        (ApplicationStatus.APPLIED, ApplicationStatus.INTERVIEW),
        (ApplicationStatus.OA, ApplicationStatus.INTERVIEW),
        (ApplicationStatus.INTERVIEW, ApplicationStatus.INTERVIEW),
        (ApplicationStatus.INTERVIEW, ApplicationStatus.OFFER),
        (ApplicationStatus.APPLIED, ApplicationStatus.WITHDRAWN),
    ],
)
def test_allowed_transitions(current: ApplicationStatus, target: ApplicationStatus) -> None:
    """Representative permitted moves return ``True``."""
    assert can_transition(current, target) is True


@pytest.mark.parametrize(
    ("current", "target"),
    [
        (ApplicationStatus.SAVED, ApplicationStatus.APPLIED),
        (ApplicationStatus.PREPARING, ApplicationStatus.OFFER),
        (ApplicationStatus.OFFER, ApplicationStatus.PREPARING),
        (ApplicationStatus.REJECTED, ApplicationStatus.APPLIED),
        (ApplicationStatus.APPLIED, ApplicationStatus.PREPARING),
    ],
)
def test_rejected_transitions(current: ApplicationStatus, target: ApplicationStatus) -> None:
    """Representative illegal jumps return ``False``."""
    assert can_transition(current, target) is False


def test_status_transition_json_round_trip() -> None:
    """A history entry serializes to JSON-safe primitives and re-parses equal."""
    transition = StatusTransition(
        from_status=ApplicationStatus.READY.value,
        to_status=ApplicationStatus.APPLIED.value,
        at=_NOW,
        forced=True,
        due=_NOW,
        note="submitted via the company site",
    )
    dumped = transition.model_dump(mode="json")
    assert datetime.fromisoformat(dumped["at"]) == _NOW
    assert dumped["forced"] is True
    assert StatusTransition.model_validate(dumped) == transition


def test_status_transition_defaults() -> None:
    """Optional fields default to unforced / no deadline / no note."""
    transition = StatusTransition(
        from_status=ApplicationStatus.SAVED.value,
        to_status=ApplicationStatus.PREPARING.value,
        at=_NOW,
    )
    assert transition.forced is False
    assert transition.due is None
    assert transition.note is None
