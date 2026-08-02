"""Onboarding Q&A and search-profile preferences (PROJECT.md §5.2).

Atlas onboards a user through a friendly Q&A that captures per-profile job-search
preferences, then stores them as structured records shared across the single
master resume. This package owns the typed preferences model
(:mod:`atlas.profiles.preferences`), the persistence layer over the ``user`` /
``profile`` tables (:mod:`atlas.profiles.repository`), the interactive wizard and
its injectable prompt boundary (:mod:`atlas.profiles.onboarding`,
:mod:`atlas.profiles.prompt`), and the package error hierarchy
(:mod:`atlas.profiles.errors`).

Preferences feed both the deterministic pre-filters and the AI scoring prompt
(PROJECT.md §5.6); the schema is multi-profile from the start though Phase 1 only
drives a single profile.
"""

from __future__ import annotations

from atlas.profiles.errors import ProfileNotFoundError, ProfilesError
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

__all__ = [
    "CompanyPreferences",
    "CompanySize",
    "CompensationPreferences",
    "LocationPreferences",
    "ProfileNotFoundError",
    "ProfilePreferences",
    "ProfilesError",
    "RemoteType",
    "Seniority",
    "WorkAuthorization",
    "create_profile",
    "get_active_profile",
    "get_profile",
    "get_user",
    "list_profiles",
    "set_active_profile",
    "update_profile",
    "upsert_user",
]
