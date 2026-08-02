"""Profile-management reporting and persistence for the Atlas CLI.

The ``atlas profile`` commands and ``atlas init`` (PROJECT.md §9, Journey A) keep
their Typer wiring thin in :mod:`atlas.cli.main` and delegate here, mirroring the
``atlas doctor`` split (:mod:`atlas.cli.doctor`): this module holds the **pure,
I/O-light logic** — building a serializable view of the stored profiles and
rendering it — plus small **persistence orchestrators** that run the onboarding
answers through the repository within one :func:`~atlas.db.session.session_scope`
transaction. Keeping the logic here means it is testable against the in-memory
``db_engine`` fixture and the scripted ``FakePrompter`` without invoking the CLI
(AGENTS.md §6.2).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel
from rich.console import Group
from rich.table import Table
from rich.text import Text

from atlas.profiles.onboarding import ProfileAnswers
from atlas.profiles.preferences import ProfilePreferences
from atlas.profiles.repository import (
    create_profile,
    get_profile,
    list_profiles,
    set_active_profile,
    update_profile,
    upsert_user,
)

if TYPE_CHECKING:
    from rich.console import RenderableType
    from sqlmodel import Session

    from atlas.profiles.onboarding import OnboardingResult

__all__ = [
    "ProfileListReport",
    "ProfileSummary",
    "apply_profile_edit",
    "build_profile_report",
    "load_profile_answers",
    "persist_onboarding",
    "persist_profile",
    "render_profiles",
    "switch_active_profile",
]


class ProfileSummary(BaseModel):
    """A compact, serializable view of one stored profile.

    Attributes:
        id: The profile's primary key.
        name: The profile's display name.
        active: Whether this is the active profile.
        target_roles: The profile's target roles (surfaced as the headline field).
        tailoring_emphasis: Themes foregrounded when tailoring.
    """

    id: int
    name: str
    active: bool
    target_roles: list[str]
    tailoring_emphasis: list[str]


class ProfileListReport(BaseModel):
    """The result of ``atlas profile list``.

    Attributes:
        profiles: One :class:`ProfileSummary` per stored profile, in creation
            order.
    """

    profiles: list[ProfileSummary]


def build_profile_report(session: Session) -> ProfileListReport:
    """Build a :class:`ProfileListReport` from every stored profile.

    Pure over the session (no console/engine I/O): reads the profiles and maps
    each into a :class:`ProfileSummary`, decoding the ``preferences`` JSON to
    surface the target roles. A blob written by a newer schema still decodes
    because :class:`~atlas.profiles.preferences.ProfilePreferences` ignores
    unknown keys.
    """
    summaries: list[ProfileSummary] = []
    for profile in list_profiles(session):
        assert profile.id is not None  # persisted rows always have an id
        preferences = ProfilePreferences.model_validate(profile.preferences)
        summaries.append(
            ProfileSummary(
                id=profile.id,
                name=profile.name,
                active=profile.active,
                target_roles=preferences.target_roles,
                tailoring_emphasis=list(profile.tailoring_emphasis),
            )
        )
    return ProfileListReport(profiles=summaries)


def load_profile_answers(session: Session, profile_id: int) -> ProfileAnswers:
    """Read a stored profile back into editable :class:`ProfileAnswers`.

    Used to pre-fill ``atlas profile edit`` so the wizard offers the current
    values as defaults.

    Raises:
        ProfileNotFoundError: If no profile has ``profile_id``.
    """
    profile = get_profile(session, profile_id)
    return ProfileAnswers(
        name=profile.name,
        preferences=ProfilePreferences.model_validate(profile.preferences),
        tailoring_emphasis=list(profile.tailoring_emphasis),
    )


def persist_profile(session: Session, answers: ProfileAnswers, *, active: bool = True) -> int:
    """Create a profile from onboarding answers, returning its id.

    Args:
        session: The open transaction to write within.
        answers: The captured profile answers (name + preferences + emphasis).
        active: Whether the new profile becomes the active one.

    Returns:
        The created profile's id.
    """
    profile = create_profile(
        session,
        name=answers.name,
        preferences=answers.preferences,
        tailoring_emphasis=answers.tailoring_emphasis,
        active=active,
    )
    assert profile.id is not None  # freshly flushed → id assigned
    return profile.id


def persist_onboarding(session: Session, result: OnboardingResult) -> int:
    """Persist a full first-run capture (user + first, active profile).

    Args:
        session: The open transaction to write within.
        result: The captured onboarding answers.

    Returns:
        The created profile's id.
    """
    upsert_user(session, name=result.user.name, email=result.user.email)
    return persist_profile(session, result.profile, active=True)


def apply_profile_edit(session: Session, profile_id: int, answers: ProfileAnswers) -> None:
    """Apply edited answers to an existing profile.

    Raises:
        ProfileNotFoundError: If no profile has ``profile_id``.
    """
    update_profile(
        session,
        profile_id,
        name=answers.name,
        preferences=answers.preferences,
        tailoring_emphasis=answers.tailoring_emphasis,
    )


def switch_active_profile(session: Session, profile_id: int) -> None:
    """Make ``profile_id`` the sole active profile.

    Raises:
        ProfileNotFoundError: If no profile has ``profile_id``.
    """
    set_active_profile(session, profile_id)


def render_profiles(report: ProfileListReport) -> RenderableType:
    """Render a :class:`ProfileListReport` as a styled Rich renderable.

    Produces a table of profiles (active mark, id, name, target roles, emphasis)
    using the shared semantic theme so it matches the rest of the CLI. An empty
    report renders a muted hint pointing at ``atlas init``. Machine-readable
    output is produced separately via :meth:`ProfileListReport.model_dump_json`.
    """
    if not report.profiles:
        return Text("No profiles yet — run `atlas init` to create one.", style="muted")
    table = Table(title="Profiles", title_style="heading", title_justify="left")
    table.add_column("", no_wrap=True)  # active glyph
    table.add_column("ID", justify="right", no_wrap=True)
    table.add_column("Name", style="accent", no_wrap=True)
    table.add_column("Target roles")
    table.add_column("Emphasis")
    for profile in report.profiles:
        glyph = Text("●", style="ok") if profile.active else Text("○", style="muted")
        table.add_row(
            glyph,
            str(profile.id),
            profile.name,
            Text(", ".join(profile.target_roles), style="muted"),
            Text(", ".join(profile.tailoring_emphasis), style="muted"),
        )
    active_note = Text("● = active profile", style="muted")
    return Group(table, Text(), active_note)
