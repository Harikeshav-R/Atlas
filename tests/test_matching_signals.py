"""Tests for the deterministic signal computation in :mod:`atlas.matching.signals`."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from atlas.db.models import JobPosting
from atlas.matching.signals import compute_signals
from atlas.matching.structure import SalaryFit, SignalStatus
from atlas.profiles.preferences import (
    CompensationPreferences,
    LocationPreferences,
    ProfilePreferences,
    RemoteType,
    WorkAuthorization,
)

_FETCHED = datetime(2026, 8, 3, tzinfo=UTC)


def _posting(
    *,
    location: str | None = None,
    remote_type: str | None = None,
    salary: dict[str, Any] | None = None,
    description: str = "",
    requirements: dict[str, Any] | None = None,
) -> JobPosting:
    return JobPosting(
        source_id=1,
        company_id=1,
        title="Backend Engineer",
        location=location,
        remote_type=remote_type,
        salary=salary or {},
        description=description,
        requirements=requirements or {},
        apply_url="https://jobs.example.test/1",
        fetched_at=_FETCHED,
        dedupe_hash="hash",
    )


# --- salary ---------------------------------------------------------------------


@pytest.mark.parametrize(
    ("salary", "floor", "target", "expected"),
    [
        ({"max": 200000}, 120000, 150000, SalaryFit.ABOVE),
        ({"max": 150000}, 120000, 150000, SalaryFit.WITHIN),
        ({"max": 140000}, 120000, 150000, SalaryFit.BELOW),
        ({"max": 100000}, 120000, 150000, SalaryFit.BELOW),  # under the floor gate
        ({"max": 130000}, 120000, None, SalaryFit.ABOVE),  # floor-only reference
        ({}, 120000, 150000, SalaryFit.UNKNOWN),  # posting has no figure
        ({"max": 150000}, None, None, SalaryFit.UNKNOWN),  # profile has no figure
    ],
)
def test_salary_fit(
    salary: dict[str, Any], floor: int | None, target: int | None, expected: SalaryFit
) -> None:
    prefs = ProfilePreferences(
        compensation=CompensationPreferences(salary_floor=floor, salary_target=target)
    )
    assert compute_signals(_posting(salary=salary), prefs).salary is expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("$150,000", SalaryFit.WITHIN),
        ("150000.0", SalaryFit.WITHIN),
        ("competitive", SalaryFit.UNKNOWN),  # unparseable string
        (True, SalaryFit.UNKNOWN),  # bool is not a figure
        (-5, SalaryFit.UNKNOWN),  # non-positive
        (None, SalaryFit.UNKNOWN),  # null value
    ],
)
def test_salary_amount_coercion(raw: Any, expected: SalaryFit) -> None:
    prefs = ProfilePreferences(compensation=CompensationPreferences(salary_target=150000))
    assert compute_signals(_posting(salary={"max": raw}), prefs).salary is expected


def test_salary_falls_through_keys_to_first_parseable() -> None:
    # "max" is unparseable, so the next key ("min") supplies the figure.
    prefs = ProfilePreferences(compensation=CompensationPreferences(salary_target=150000))
    posting = _posting(salary={"max": "n/a", "min": 150000})
    assert compute_signals(posting, prefs).salary is SalaryFit.WITHIN


# --- location -------------------------------------------------------------------


def test_location_remote_type_match() -> None:
    prefs = ProfilePreferences(location=LocationPreferences(remote_types=[RemoteType.REMOTE]))
    assert compute_signals(_posting(remote_type="remote"), prefs).location is SignalStatus.MATCH


def test_location_onsite_mismatch_for_remote_only_profile() -> None:
    prefs = ProfilePreferences(location=LocationPreferences(remote_types=[RemoteType.REMOTE]))
    assert compute_signals(_posting(remote_type="onsite"), prefs).location is SignalStatus.MISMATCH


def test_location_onsite_not_mismatch_when_willing_to_relocate() -> None:
    prefs = ProfilePreferences(
        location=LocationPreferences(remote_types=[RemoteType.REMOTE], willing_to_relocate=True)
    )
    # Willing to relocate → an on-site posting is left to the AI, not a mismatch.
    assert compute_signals(_posting(remote_type="onsite"), prefs).location is SignalStatus.UNKNOWN


def test_location_city_match() -> None:
    prefs = ProfilePreferences(location=LocationPreferences(cities=["Austin"]))
    posting = _posting(location="Austin, TX")
    assert compute_signals(posting, prefs).location is SignalStatus.MATCH


def test_location_city_no_match_is_unknown() -> None:
    prefs = ProfilePreferences(location=LocationPreferences(cities=["  "]))  # blank city ignored
    posting = _posting(location="Boston, MA")
    assert compute_signals(posting, prefs).location is SignalStatus.UNKNOWN


def test_location_unknown_without_preferences() -> None:
    prefs = ProfilePreferences()
    assert compute_signals(_posting(remote_type="remote"), prefs).location is SignalStatus.UNKNOWN


def test_location_hybrid_not_accepted_but_not_onsite_is_unknown() -> None:
    # A hybrid posting that isn't in the accepted set, and isn't on-site, stays
    # UNKNOWN (only explicit on-site mismatches a remote-only profile).
    prefs = ProfilePreferences(location=LocationPreferences(remote_types=[RemoteType.REMOTE]))
    assert compute_signals(_posting(remote_type="hybrid"), prefs).location is SignalStatus.UNKNOWN


# --- work authorization ---------------------------------------------------------


def test_work_auth_unknown_when_no_sponsorship_needed() -> None:
    prefs = ProfilePreferences()
    posting = _posting(description="No visa sponsorship available.")
    assert compute_signals(posting, prefs).work_auth is SignalStatus.UNKNOWN


def test_work_auth_mismatch_when_sponsorship_needed_and_denied() -> None:
    prefs = ProfilePreferences(work_authorization=WorkAuthorization(needs_sponsorship=True))
    posting = _posting(description="This role requires US citizenship.")
    assert compute_signals(posting, prefs).work_auth is SignalStatus.MISMATCH


def test_work_auth_match_when_sponsorship_needed_and_not_denied() -> None:
    prefs = ProfilePreferences(work_authorization=WorkAuthorization(needs_sponsorship=True))
    posting = _posting(description="We welcome applicants from all backgrounds.")
    assert compute_signals(posting, prefs).work_auth is SignalStatus.MATCH


# --- deal-breakers --------------------------------------------------------------


def test_dealbreaker_hits_from_description_and_requirements() -> None:
    prefs = ProfilePreferences(deal_breakers=["on-call", "  ", "PHP"])
    posting = _posting(
        description="Rotating ON-CALL schedule.",
        requirements={"must": ["PHP experience"], "nice": ["Go"]},
    )
    hits = compute_signals(posting, prefs).dealbreakers
    # Case-insensitive, blank deal-breaker ignored, profile order preserved.
    assert hits == ["on-call", "PHP"]


def test_dealbreaker_no_hits() -> None:
    prefs = ProfilePreferences(deal_breakers=["on-call"])
    posting = _posting(description="Daytime only, no pager.")
    assert compute_signals(posting, prefs).dealbreakers == []


def test_dealbreaker_deduplicates_repeated_match() -> None:
    prefs = ProfilePreferences(deal_breakers=["travel", "travel"])
    posting = _posting(description="Frequent travel required.")
    assert compute_signals(posting, prefs).dealbreakers == ["travel"]


def test_posting_text_ignores_non_list_requirement_values() -> None:
    # A malformed requirements blob (a string, not a list) is tolerated.
    prefs = ProfilePreferences(deal_breakers=["php"])
    posting = _posting(description="", requirements={"must": "PHP", "nice": ["php"]})
    # "must" (a str) is skipped; "nice" (a list) still yields the hit.
    assert compute_signals(posting, prefs).dealbreakers == ["php"]
