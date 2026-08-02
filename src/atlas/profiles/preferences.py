"""Typed, structured job-search preferences for a single search profile.

A :class:`ProfilePreferences` captures everything the onboarding Q&A asks about a
profile (PROJECT.md §5.2): target roles, seniority, specialization, location and
remote posture, compensation, work authorization, company preferences, and
deal-breakers. It is a plain Pydantic model with no I/O, so it is trivially
testable and reusable by the matching engine (PROJECT.md §5.6) and the tailoring
prompt.

It serializes into the ``preferences`` JSON column of the ``profile`` table
(:class:`atlas.db.models.Profile`) via :meth:`~pydantic.BaseModel.model_dump`
(``mode="json"`` so enums become their string values) and is read back with
:meth:`~pydantic.BaseModel.model_validate`. Every field is defaulted, so an empty
object is a valid (blank) set of preferences and older stored objects still load
as the schema grows — closed domains are modelled as string enums, open-ended
ones as free-text lists.

Tailoring emphasis is intentionally **not** modelled here: it maps to the
separate :attr:`atlas.db.models.Profile.tailoring_emphasis` column, not the
``preferences`` blob.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "CompanyPreferences",
    "CompanySize",
    "CompensationPreferences",
    "LocationPreferences",
    "ProfilePreferences",
    "RemoteType",
    "Seniority",
    "WorkAuthorization",
]


class _Base(BaseModel):
    """Base model that ignores unknown keys (forward-compatible preferences).

    Mirrors :class:`atlas.config.schema._Base`: as the preferences schema grows,
    an object stored by an older version still loads (its now-unknown keys are
    dropped rather than rejected).
    """

    model_config = ConfigDict(extra="ignore")


class Seniority(StrEnum):
    """A seniority / skill level a profile targets (PROJECT.md §5.2)."""

    INTERN = "intern"
    NEW_GRAD = "new_grad"
    JUNIOR = "junior"
    MID = "mid"
    SENIOR = "senior"
    STAFF = "staff"
    PRINCIPAL = "principal"


class RemoteType(StrEnum):
    """An acceptable work arrangement for a profile (PROJECT.md §5.2)."""

    ONSITE = "onsite"
    HYBRID = "hybrid"
    REMOTE = "remote"


class CompanySize(StrEnum):
    """A company-size bucket a profile prefers (PROJECT.md §5.2)."""

    STARTUP = "startup"
    MIDSIZE = "midsize"
    LARGE = "large"
    ENTERPRISE = "enterprise"


class LocationPreferences(_Base):
    """Where a profile is willing to work.

    Attributes:
        cities: Acceptable cities/metros (free text), if any.
        remote_types: Acceptable work arrangements (on-site/hybrid/remote).
        remote_regions: For remote roles, acceptable regions/timezone bands
            (e.g. ``"US"``, ``"EU"``, ``"Americas"``).
        timezone: A timezone constraint, if any (e.g. ``"UTC-8..UTC-5"``).
        willing_to_relocate: Whether the user will relocate for the right role.
    """

    cities: list[str] = Field(default_factory=list)
    remote_types: list[RemoteType] = Field(default_factory=list)
    remote_regions: list[str] = Field(default_factory=list)
    timezone: str | None = None
    willing_to_relocate: bool = False


class CompensationPreferences(_Base):
    """Compensation expectations for a profile.

    Attributes:
        salary_floor: Minimum acceptable base salary (in :attr:`currency`), if set.
        salary_target: Desired base salary (in :attr:`currency`), if set.
        currency: ISO-4217-ish currency code for the salary figures.
        equity_important: Whether equity weighs meaningfully in the decision.
        bonus_important: Whether a bonus weighs meaningfully in the decision.
    """

    salary_floor: int | None = None
    salary_target: int | None = None
    currency: str = "USD"
    equity_important: bool = False
    bonus_important: bool = False


class WorkAuthorization(_Base):
    """Work-authorization / visa needs that drive filtering (never fabricated).

    Attributes:
        status: The user's authorization status in free text (e.g.
            ``"US citizen"``, ``"H-1B"``, ``"needs sponsorship"``).
        needs_sponsorship: Whether the user requires visa sponsorship.
    """

    status: str | None = None
    needs_sponsorship: bool = False


class CompanyPreferences(_Base):
    """Company-level preferences for a profile.

    Attributes:
        sizes: Preferred company-size buckets.
        industries_like: Industries the user is drawn to (free text).
        industries_avoid: Industries the user wants to avoid (free text).
        culture_keywords: Mission/culture keywords that resonate (free text).
    """

    sizes: list[CompanySize] = Field(default_factory=list)
    industries_like: list[str] = Field(default_factory=list)
    industries_avoid: list[str] = Field(default_factory=list)
    culture_keywords: list[str] = Field(default_factory=list)


class ProfilePreferences(_Base):
    """The full, structured preferences captured for one search profile.

    Stored in :attr:`atlas.db.models.Profile.preferences`. Feeds both the
    deterministic pre-filters and the AI scoring prompt (PROJECT.md §5.2, §5.6).

    Attributes:
        target_roles: Primary target roles/titles (e.g. ``"Backend Engineer"``).
        role_variants: Acceptable title variants for those roles.
        seniority_levels: Seniority levels the profile targets.
        specializations: Fields/specializations (backend, ML, infra, …).
        location: Location and remote-work preferences.
        compensation: Compensation expectations.
        work_authorization: Work-authorization / visa needs.
        company: Company-level preferences.
        deal_breakers: Hard deal-breakers (e.g. ``"no on-call"``).
    """

    target_roles: list[str] = Field(default_factory=list)
    role_variants: list[str] = Field(default_factory=list)
    seniority_levels: list[Seniority] = Field(default_factory=list)
    specializations: list[str] = Field(default_factory=list)
    location: LocationPreferences = Field(default_factory=LocationPreferences)
    compensation: CompensationPreferences = Field(default_factory=CompensationPreferences)
    work_authorization: WorkAuthorization = Field(default_factory=WorkAuthorization)
    company: CompanyPreferences = Field(default_factory=CompanyPreferences)
    deal_breakers: list[str] = Field(default_factory=list)
