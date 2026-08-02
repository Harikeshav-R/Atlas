"""Tests for the typed preferences model in :mod:`atlas.profiles.preferences`."""

from __future__ import annotations

from atlas.profiles import ProfileNotFoundError, ProfilesError
from atlas.profiles.preferences import (
    CompanyPreferences,
    CompanySize,
    CompensationPreferences,
    LocationPreferences,
    ProfilePreferences,
    RemoteType,
    Seniority,
    WorkAuthorization,
)


def test_defaults_are_empty_and_valid() -> None:
    prefs = ProfilePreferences()
    assert prefs.target_roles == []
    assert prefs.role_variants == []
    assert prefs.seniority_levels == []
    assert prefs.specializations == []
    assert prefs.deal_breakers == []
    # Nested sub-models default to their own blank instances.
    assert prefs.location.cities == []
    assert prefs.location.remote_types == []
    assert prefs.location.willing_to_relocate is False
    assert prefs.compensation.salary_floor is None
    assert prefs.compensation.currency == "USD"
    assert prefs.work_authorization.needs_sponsorship is False
    assert prefs.company.sizes == []


def test_enum_values_are_the_wire_strings() -> None:
    # ``mode="json"`` serialization relies on these string values.
    assert Seniority.NEW_GRAD.value == "new_grad"
    assert RemoteType.REMOTE.value == "remote"
    assert CompanySize.ENTERPRISE.value == "enterprise"


def test_full_preferences_json_round_trip() -> None:
    prefs = ProfilePreferences(
        target_roles=["Backend Engineer"],
        role_variants=["Software Engineer, Backend"],
        seniority_levels=[Seniority.MID, Seniority.SENIOR],
        specializations=["backend", "infra"],
        location=LocationPreferences(
            cities=["Seattle"],
            remote_types=[RemoteType.REMOTE, RemoteType.HYBRID],
            remote_regions=["US"],
            timezone="UTC-8..UTC-5",
            willing_to_relocate=True,
        ),
        compensation=CompensationPreferences(
            salary_floor=150000,
            salary_target=180000,
            currency="USD",
            equity_important=True,
            bonus_important=False,
        ),
        work_authorization=WorkAuthorization(status="US citizen", needs_sponsorship=False),
        company=CompanyPreferences(
            sizes=[CompanySize.STARTUP, CompanySize.MIDSIZE],
            industries_like=["fintech"],
            industries_avoid=["adtech"],
            culture_keywords=["ownership"],
        ),
        deal_breakers=["no on-call"],
    )

    dumped = prefs.model_dump(mode="json")
    # Enums serialize to their string values so they land cleanly in the JSON column.
    assert dumped["seniority_levels"] == ["mid", "senior"]
    assert dumped["location"]["remote_types"] == ["remote", "hybrid"]
    assert dumped["company"]["sizes"] == ["startup", "midsize"]

    restored = ProfilePreferences.model_validate(dumped)
    assert restored == prefs


def test_extra_keys_are_ignored_for_forward_compatibility() -> None:
    # A blob written by a newer schema (unknown keys) still loads.
    restored = ProfilePreferences.model_validate(
        {
            "target_roles": ["ML Engineer"],
            "future_field": "ignored",
            "location": {"cities": ["Remote"], "unknown": 1},
        }
    )
    assert restored.target_roles == ["ML Engineer"]
    assert restored.location.cities == ["Remote"]


def test_profile_not_found_error_carries_id_and_is_profiles_error() -> None:
    exc = ProfileNotFoundError(42)
    assert exc.profile_id == 42
    assert "42" in str(exc)
    assert isinstance(exc, ProfilesError)
