"""Tests for the onboarding wizard in :mod:`atlas.profiles.onboarding`."""

from __future__ import annotations

from atlas.profiles.onboarding import (
    OnboardingResult,
    ProfileAnswers,
    UserAnswers,
    ask_profile,
    ask_user,
    run_onboarding,
)
from atlas.profiles.preferences import (
    CompanySize,
    ProfilePreferences,
    RemoteType,
    Seniority,
)
from tests.conftest import FakePrompter

# The full happy-path text answers, in the exact order the wizard asks them.
_FULL_TEXTS = [
    "Sam Lee",  # name
    "sam@example.com",  # email
    "Backend Engineer",  # profile name
    "Backend Engineer, Platform Engineer",  # target roles
    "Software Engineer, Backend",  # title variants
    "mid, senior",  # seniority levels
    "backend, infra",  # specializations
    "Seattle",  # cities
    "remote, hybrid",  # work arrangements
    "US, EU",  # remote regions
    "UTC-8..UTC-5",  # timezone
    "150000",  # salary floor
    "180000",  # salary target
    "USD",  # currency
    "US citizen",  # work authorization status
    "startup, midsize",  # company sizes
    "fintech",  # industries like
    "adtech",  # industries avoid
    "ownership",  # culture keywords
    "no on-call",  # deal-breakers
    "distributed systems",  # tailoring emphasis
]
# The yes/no answers, in order: relocate, equity, bonus, sponsorship.
_FULL_BOOLS = [True, True, False, False]


def test_run_onboarding_happy_path_captures_everything() -> None:
    prompter = FakePrompter(texts=_FULL_TEXTS, bools=_FULL_BOOLS)

    result = run_onboarding(prompter)

    assert result.user == UserAnswers(name="Sam Lee", email="sam@example.com")
    profile = result.profile
    assert profile.name == "Backend Engineer"
    assert profile.tailoring_emphasis == ["distributed systems"]
    prefs = profile.preferences
    assert prefs.target_roles == ["Backend Engineer", "Platform Engineer"]
    # The comma in the variants answer splits it into two trimmed items.
    assert prefs.role_variants == ["Software Engineer", "Backend"]
    assert prefs.seniority_levels == [Seniority.MID, Seniority.SENIOR]
    assert prefs.specializations == ["backend", "infra"]
    assert prefs.location.cities == ["Seattle"]
    assert prefs.location.remote_types == [RemoteType.REMOTE, RemoteType.HYBRID]
    assert prefs.location.remote_regions == ["US", "EU"]
    assert prefs.location.timezone == "UTC-8..UTC-5"
    assert prefs.location.willing_to_relocate is True
    assert prefs.compensation.salary_floor == 150000
    assert prefs.compensation.salary_target == 180000
    assert prefs.compensation.currency == "USD"
    assert prefs.compensation.equity_important is True
    assert prefs.compensation.bonus_important is False
    assert prefs.work_authorization.status == "US citizen"
    assert prefs.work_authorization.needs_sponsorship is False
    assert prefs.company.sizes == [CompanySize.STARTUP, CompanySize.MIDSIZE]
    assert prefs.company.industries_like == ["fintech"]
    assert prefs.company.industries_avoid == ["adtech"]
    assert prefs.company.culture_keywords == ["ownership"]
    assert prefs.deal_breakers == ["no on-call"]


def test_run_onboarding_all_optionals_skipped() -> None:
    # Everything optional is blank; only the three required fields are answered.
    texts = [
        "Sam",  # name
        "",  # email skipped
        "Grad Roles",  # profile name
        "New Grad SWE",  # target roles (required)
        "",  # variants
        "",  # seniority
        "",  # specializations
        "",  # cities
        "",  # arrangements
        "",  # regions
        "",  # timezone
        "",  # salary floor
        "",  # salary target
        "USD",  # currency (required text)
        "",  # work auth status
        "",  # company sizes
        "",  # industries like
        "",  # industries avoid
        "",  # culture keywords
        "",  # deal-breakers
        "",  # tailoring emphasis
    ]
    bools = [False, False, False, False]
    result = run_onboarding(FakePrompter(texts=texts, bools=bools))

    assert result.user == UserAnswers(name="Sam", email=None)
    prefs = result.profile.preferences
    assert prefs.target_roles == ["New Grad SWE"]
    assert prefs.role_variants == []
    assert prefs.seniority_levels == []
    assert prefs.location.cities == []
    assert prefs.location.timezone is None
    assert prefs.compensation.salary_floor is None
    assert prefs.work_authorization.status is None
    assert prefs.company.sizes == []
    assert result.profile.tailoring_emphasis == []


def test_required_name_reprompts_until_nonempty() -> None:
    # Blank/whitespace name answers are rejected until a real one is given; the
    # trailing "" is the (optional) email.
    prompter = FakePrompter(texts=["", "   ", "Sam", ""], bools=[])
    user = ask_user(prompter)
    assert user == UserAnswers(name="Sam", email=None)
    # The name question was re-asked for each blank answer before succeeding.
    assert sum(1 for message, _ in prompter.asked if message == "Your name") == 3


def test_required_target_role_reprompts() -> None:
    # First roles answer is blank, so the wizard re-asks with the fallback prompt.
    texts = [
        "First Profile",  # profile name
        "",  # target roles (blank → re-prompt)
        "Backend Engineer",  # retry answer
        "",  # variants
        "",  # seniority
        "",  # specializations
        "",  # cities
        "",  # arrangements
        "",  # regions
        "",  # timezone
        "",  # salary floor
        "",  # salary target
        "USD",  # currency
        "",  # work auth status
        "",  # company sizes
        "",  # industries like
        "",  # industries avoid
        "",  # culture keywords
        "",  # deal-breakers
        "",  # tailoring emphasis
    ]
    prompter = FakePrompter(texts=texts, bools=[False, False, False, False])
    profile = ask_profile(prompter)
    assert profile.preferences.target_roles == ["Backend Engineer"]
    assert any(message == "Enter at least one target role" for message, _ in prompter.asked)


def test_optional_int_reprompts_on_non_numeric() -> None:
    # A non-numeric salary floor is rejected, then a valid number is accepted.
    texts = [
        "P",  # profile name
        "Role",  # target roles
        "",  # variants
        "",  # seniority
        "",  # specializations
        "",  # cities
        "",  # arrangements
        "",  # regions
        "",  # timezone
        "not-a-number",  # salary floor (invalid → re-prompt)
        "120000",  # salary floor retry
        "",  # salary target
        "USD",  # currency
        "",  # work auth status
        "",  # company sizes
        "",  # industries like
        "",  # industries avoid
        "",  # culture keywords
        "",  # deal-breakers
        "",  # tailoring emphasis
    ]
    prompter = FakePrompter(texts=texts, bools=[False, False, False, False])
    profile = ask_profile(prompter)
    assert profile.preferences.compensation.salary_floor == 120000
    assert profile.preferences.compensation.salary_target is None


def test_enum_list_reprompts_on_unknown_token() -> None:
    # An unknown seniority token re-prompts the whole field.
    texts = [
        "P",  # profile name
        "Role",  # target roles
        "",  # variants
        "wizard, senior",  # seniority (bad token → re-prompt)
        "senior",  # seniority retry
        "",  # specializations
        "",  # cities
        "",  # arrangements
        "",  # regions
        "",  # timezone
        "",  # salary floor
        "",  # salary target
        "USD",  # currency
        "",  # work auth status
        "",  # company sizes
        "",  # industries like
        "",  # industries avoid
        "",  # culture keywords
        "",  # deal-breakers
        "",  # tailoring emphasis
    ]
    prompter = FakePrompter(texts=texts, bools=[False, False, False, False])
    profile = ask_profile(prompter)
    assert profile.preferences.seniority_levels == [Seniority.SENIOR]


def test_existing_answers_prefill_defaults() -> None:
    existing = OnboardingResult(
        user=UserAnswers(name="Sam", email="sam@example.com"),
        profile=ProfileAnswers(
            name="Backend Engineer",
            preferences=ProfilePreferences(
                target_roles=["Backend Engineer"],
                seniority_levels=[Seniority.SENIOR],
            ),
            tailoring_emphasis=["distributed systems"],
        ),
    )
    prompter = FakePrompter(texts=_FULL_TEXTS, bools=_FULL_BOOLS)

    run_onboarding(prompter, existing=existing)

    asked = dict(prompter.asked)
    # Edit mode offers the current values as defaults.
    assert asked["Your name"] == "Sam"
    assert asked["Your email (optional)"] == "sam@example.com"
    assert asked["Profile name (e.g. Backend Engineer)"] == "Backend Engineer"
    # Enum + list defaults are rendered back as their comma-joined tokens.
    assert asked[
        "Seniority levels [intern/new_grad/junior/mid/senior/staff/principal] (optional)"
    ] == ("senior")
    assert asked["Tailoring emphasis — themes to foreground (optional)"] == "distributed systems"
