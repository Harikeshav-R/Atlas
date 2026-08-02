"""The onboarding Q&A wizard (PROJECT.md §5.2, Journey A).

:func:`run_onboarding` walks a user through the questions that populate the single
:class:`~atlas.db.models.User` record and one search
:class:`~atlas.db.models.Profile`. It is **pure over a**
:class:`~atlas.profiles.prompt.Prompter`: it asks questions and assembles typed
answers but performs no database or console I/O of its own, so the whole flow is
exercised by a scripted fake in the hermetic suite (AGENTS.md §6.2). Persistence
is the caller's job (the CLI wraps the returned answers in
:func:`atlas.db.session.session_scope` and the repository functions).

All parsing lives here, over just two prompter primitives (free-text and yes/no):
comma-separated lists, optional integers, and case-insensitive enum tokens are
parsed and re-prompted on invalid input. Passing an ``existing`` value pre-fills
every answer as its default, so the same wizard drives first-run onboarding and
later edits (``atlas profile edit``).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, TypeVar

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

if TYPE_CHECKING:
    from enum import StrEnum

    from atlas.profiles.prompt import Prompter

__all__ = [
    "OnboardingResult",
    "ProfileAnswers",
    "UserAnswers",
    "ask_profile",
    "ask_user",
    "run_onboarding",
]

_E = TypeVar("_E", bound="StrEnum")


@dataclass
class UserAnswers:
    """The single user's identity captured during onboarding.

    Attributes:
        name: The user's display name.
        email: The user's contact email, or ``None`` if skipped.
    """

    name: str
    email: str | None = None


@dataclass
class ProfileAnswers:
    """One search profile's name, preferences, and tailoring emphasis.

    Attributes:
        name: The profile's display name.
        preferences: The structured job-search preferences.
        tailoring_emphasis: Themes to foreground when tailoring.
    """

    name: str
    preferences: ProfilePreferences = field(default_factory=ProfilePreferences)
    tailoring_emphasis: list[str] = field(default_factory=list)


@dataclass
class OnboardingResult:
    """The full first-run capture: the user plus their first profile."""

    user: UserAnswers
    profile: ProfileAnswers


def _split_list(raw: str) -> list[str]:
    """Split a comma-separated answer into trimmed, non-empty items."""
    return [item.strip() for item in raw.split(",") if item.strip()]


def _join_list(items: list[str]) -> str:
    """Render a list back to a comma-separated default for edit-mode pre-fill."""
    return ", ".join(items)


def _ask_required_text(prompter: Prompter, message: str, *, default: str) -> str:
    """Ask for text that must be non-empty, re-prompting until it is."""
    while True:
        answer = prompter.ask_text(message, default=default).strip()
        if answer:
            return answer


def _ask_list(prompter: Prompter, message: str, *, default: list[str]) -> list[str]:
    """Ask for an optional comma-separated list (empty answer → empty list)."""
    return _split_list(prompter.ask_text(message, default=_join_list(default)))


def _ask_optional_int(prompter: Prompter, message: str, *, default: int | None) -> int | None:
    """Ask for an optional integer, re-prompting on non-numeric input.

    An empty answer clears the value (``None``); a valid integer is returned;
    anything else re-prompts.
    """
    default_text = "" if default is None else str(default)
    while True:
        answer = prompter.ask_text(message, default=default_text).strip()
        if not answer:
            return None
        try:
            return int(answer)
        except ValueError:
            continue


def _ask_enum_list(
    prompter: Prompter, message: str, enum_cls: type[_E], *, default: list[_E]
) -> list[_E]:
    """Ask for an optional list of enum tokens, re-prompting on any unknown one.

    Tokens are matched case-insensitively against the enum's values; an empty
    answer yields an empty list, and one bad token re-prompts the whole field.
    """
    default_text = _join_list([member.value for member in default])
    while True:
        tokens = _split_list(prompter.ask_text(message, default=default_text))
        try:
            return [enum_cls(token.lower()) for token in tokens]
        except ValueError:
            continue


def ask_user(prompter: Prompter, *, existing: UserAnswers | None = None) -> UserAnswers:
    """Ask for the user's name and (optional) email.

    Args:
        prompter: The question-asking boundary.
        existing: Current answers to pre-fill as defaults (edit mode), or ``None``.

    Returns:
        The captured :class:`UserAnswers`.
    """
    name = _ask_required_text(prompter, "Your name", default=existing.name if existing else "")
    email = prompter.ask_text(
        "Your email (optional)", default=existing.email if existing and existing.email else ""
    ).strip()
    return UserAnswers(name=name, email=email or None)


def ask_profile(prompter: Prompter, *, existing: ProfileAnswers | None = None) -> ProfileAnswers:
    """Ask the full per-profile preference Q&A (PROJECT.md §5.2).

    Args:
        prompter: The question-asking boundary.
        existing: Current answers to pre-fill as defaults (edit mode), or ``None``.

    Returns:
        The captured :class:`ProfileAnswers`.
    """
    base = existing.preferences if existing else ProfilePreferences()

    name = _ask_required_text(
        prompter, "Profile name (e.g. Backend Engineer)", default=existing.name if existing else ""
    )

    target_roles = _ask_list(prompter, "Target roles/titles (comma-separated)", default=[])
    while not target_roles:
        # At least one target role anchors matching; keep asking until we have one.
        target_roles = _ask_list(prompter, "Enter at least one target role", default=[])

    preferences = ProfilePreferences(
        target_roles=target_roles,
        role_variants=_ask_list(
            prompter, "Acceptable title variants (optional)", default=base.role_variants
        ),
        seniority_levels=_ask_enum_list(
            prompter,
            f"Seniority levels {_enum_hint(Seniority)} (optional)",
            Seniority,
            default=base.seniority_levels,
        ),
        specializations=_ask_list(
            prompter, "Specializations, e.g. backend, ML (optional)", default=base.specializations
        ),
        location=_ask_location(prompter, base.location),
        compensation=_ask_compensation(prompter, base.compensation),
        work_authorization=_ask_work_authorization(prompter, base.work_authorization),
        company=_ask_company(prompter, base.company),
        deal_breakers=_ask_list(prompter, "Deal-breakers (optional)", default=base.deal_breakers),
    )
    tailoring_emphasis = _ask_list(
        prompter,
        "Tailoring emphasis — themes to foreground (optional)",
        default=existing.tailoring_emphasis if existing else [],
    )
    return ProfileAnswers(name=name, preferences=preferences, tailoring_emphasis=tailoring_emphasis)


def _ask_location(prompter: Prompter, base: LocationPreferences) -> LocationPreferences:
    """Ask the location/remote sub-questions."""
    cities = _ask_list(prompter, "Preferred cities (optional)", default=base.cities)
    remote_types = _ask_enum_list(
        prompter,
        f"Work arrangements {_enum_hint(RemoteType)} (optional)",
        RemoteType,
        default=base.remote_types,
    )
    remote_regions = _ask_list(
        prompter, "Remote regions, e.g. US, EU (optional)", default=base.remote_regions
    )
    timezone = prompter.ask_text(
        "Timezone constraint (optional)", default=base.timezone or ""
    ).strip()
    willing_to_relocate = prompter.ask_bool(
        "Willing to relocate?", default=base.willing_to_relocate
    )
    return LocationPreferences(
        cities=cities,
        remote_types=remote_types,
        remote_regions=remote_regions,
        timezone=timezone or None,
        willing_to_relocate=willing_to_relocate,
    )


def _ask_compensation(prompter: Prompter, base: CompensationPreferences) -> CompensationPreferences:
    """Ask the compensation sub-questions."""
    salary_floor = _ask_optional_int(
        prompter, "Salary floor (optional, number)", default=base.salary_floor
    )
    salary_target = _ask_optional_int(
        prompter, "Salary target (optional, number)", default=base.salary_target
    )
    currency = _ask_required_text(prompter, "Salary currency", default=base.currency)
    equity_important = prompter.ask_bool("Is equity important?", default=base.equity_important)
    bonus_important = prompter.ask_bool("Is a bonus important?", default=base.bonus_important)
    return CompensationPreferences(
        salary_floor=salary_floor,
        salary_target=salary_target,
        currency=currency,
        equity_important=equity_important,
        bonus_important=bonus_important,
    )


def _ask_work_authorization(prompter: Prompter, base: WorkAuthorization) -> WorkAuthorization:
    """Ask the work-authorization sub-questions."""
    status = prompter.ask_text(
        "Work authorization status (optional)", default=base.status or ""
    ).strip()
    needs_sponsorship = prompter.ask_bool(
        "Do you need visa sponsorship?", default=base.needs_sponsorship
    )
    return WorkAuthorization(status=status or None, needs_sponsorship=needs_sponsorship)


def _ask_company(prompter: Prompter, base: CompanyPreferences) -> CompanyPreferences:
    """Ask the company-preference sub-questions."""
    sizes = _ask_enum_list(
        prompter,
        f"Company sizes {_enum_hint(CompanySize)} (optional)",
        CompanySize,
        default=base.sizes,
    )
    industries_like = _ask_list(
        prompter, "Industries you like (optional)", default=base.industries_like
    )
    industries_avoid = _ask_list(
        prompter, "Industries to avoid (optional)", default=base.industries_avoid
    )
    culture_keywords = _ask_list(
        prompter, "Culture keywords (optional)", default=base.culture_keywords
    )
    return CompanyPreferences(
        sizes=sizes,
        industries_like=industries_like,
        industries_avoid=industries_avoid,
        culture_keywords=culture_keywords,
    )


def _enum_hint(enum_cls: type[StrEnum]) -> str:
    """Return a ``[a/b/c]`` hint listing an enum's accepted tokens."""
    return "[" + "/".join(member.value for member in enum_cls) + "]"


def run_onboarding(
    prompter: Prompter, *, existing: OnboardingResult | None = None
) -> OnboardingResult:
    """Run the full first-run Q&A: the user plus their first profile.

    Args:
        prompter: The question-asking boundary.
        existing: Current answers to pre-fill as defaults, or ``None`` for a
            fresh run.

    Returns:
        The captured :class:`OnboardingResult` (not yet persisted).
    """
    user = ask_user(prompter, existing=existing.user if existing else None)
    profile = ask_profile(prompter, existing=existing.profile if existing else None)
    return OnboardingResult(user=user, profile=profile)
