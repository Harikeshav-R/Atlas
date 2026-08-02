"""Persistence for the single user and search profiles (PROJECT.md §5.2, §6).

These are thin, pure functions over an **open** :class:`~sqlmodel.Session`: the
caller opens the transaction with :func:`atlas.db.session.session_scope`, calls
one or more of these, and the scope commits (or rolls back) on exit — the same
single-write-path convention the data layer already follows. Nothing here opens
its own session or engine, so the functions compose freely within one
transaction and stay trivially testable against the in-memory ``db_engine``
fixture (AGENTS.md §6.2).

Two invariants Atlas relies on are enforced here in code (not by database
constraints, per the :class:`~atlas.db.models.User` / :class:`Profile`
docstrings):

- **Single user** — Atlas is single-user, so :func:`upsert_user` updates the one
  existing row rather than inserting a second.
- **Single active profile** — creating or switching the active profile
  deactivates every other profile in the same transaction, so exactly one
  profile is active at a time.

Typed :class:`~atlas.profiles.preferences.ProfilePreferences` are serialized into
the ``profile.preferences`` JSON column on write; callers read them back with
:meth:`ProfilePreferences.model_validate`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlmodel import col, select

from atlas.db.models import Profile, User
from atlas.profiles.errors import ProfileNotFoundError

if TYPE_CHECKING:
    from sqlmodel import Session

    from atlas.profiles.preferences import ProfilePreferences

__all__ = [
    "create_profile",
    "get_active_profile",
    "get_profile",
    "get_user",
    "list_profiles",
    "set_active_profile",
    "update_profile",
    "upsert_user",
]


def get_user(session: Session) -> User | None:
    """Return the single Atlas user, or ``None`` if onboarding has not run yet."""
    return session.exec(select(User)).first()


def upsert_user(session: Session, *, name: str, email: str | None = None) -> User:
    """Create the user, or update the existing one's name/email (single-user).

    Args:
        session: The open session/transaction to write within.
        name: The user's display name.
        email: The user's contact email, if provided.

    Returns:
        The created or updated :class:`~atlas.db.models.User` (id assigned).
    """
    user = get_user(session)
    if user is None:
        user = User(name=name, email=email)
        session.add(user)
    else:
        user.name = name
        user.email = email
        session.add(user)
    session.flush()
    return user


def list_profiles(session: Session) -> list[Profile]:
    """Return all search profiles ordered by id (creation order)."""
    return list(session.exec(select(Profile).order_by(col(Profile.id))).all())


def get_profile(session: Session, profile_id: int) -> Profile:
    """Return the profile with ``profile_id``.

    Raises:
        ProfileNotFoundError: If no profile has that id.
    """
    profile = session.get(Profile, profile_id)
    if profile is None:
        raise ProfileNotFoundError(profile_id)
    return profile


def get_active_profile(session: Session) -> Profile | None:
    """Return the active profile, or ``None`` if none is active."""
    return session.exec(select(Profile).where(Profile.active)).first()


def create_profile(
    session: Session,
    *,
    name: str,
    preferences: ProfilePreferences,
    tailoring_emphasis: list[str] | None = None,
    active: bool = True,
) -> Profile:
    """Create a new search profile from typed preferences.

    Args:
        session: The open session/transaction to write within.
        name: The profile's display name (e.g. ``"Backend Engineer"``).
        preferences: The structured preferences; serialized into the JSON column.
        tailoring_emphasis: Themes to foreground when tailoring, if any.
        active: Whether the new profile becomes the active one. When ``True``,
            every other profile is deactivated in the same transaction so exactly
            one profile stays active.

    Returns:
        The created :class:`~atlas.db.models.Profile` (id assigned).
    """
    profile = Profile(
        name=name,
        preferences=preferences.model_dump(mode="json"),
        tailoring_emphasis=list(tailoring_emphasis or []),
        active=active,
    )
    session.add(profile)
    session.flush()
    if active:
        _deactivate_others(session, keep_id=profile.id)
    return profile


def update_profile(
    session: Session,
    profile_id: int,
    *,
    name: str | None = None,
    preferences: ProfilePreferences | None = None,
    tailoring_emphasis: list[str] | None = None,
) -> Profile:
    """Update a profile's editable fields; ``None`` arguments are left unchanged.

    Args:
        session: The open session/transaction to write within.
        profile_id: The id of the profile to update.
        name: New display name, or ``None`` to keep the current one.
        preferences: New preferences, or ``None`` to keep the current ones.
        tailoring_emphasis: New emphasis list, or ``None`` to keep the current one.

    Returns:
        The updated :class:`~atlas.db.models.Profile`.

    Raises:
        ProfileNotFoundError: If no profile has that id.
    """
    profile = get_profile(session, profile_id)
    if name is not None:
        profile.name = name
    if preferences is not None:
        profile.preferences = preferences.model_dump(mode="json")
    if tailoring_emphasis is not None:
        profile.tailoring_emphasis = list(tailoring_emphasis)
    session.add(profile)
    session.flush()
    return profile


def set_active_profile(session: Session, profile_id: int) -> Profile:
    """Make ``profile_id`` the sole active profile.

    Activates the target and deactivates every other profile in the same
    transaction (the single-active invariant).

    Args:
        session: The open session/transaction to write within.
        profile_id: The id of the profile to activate.

    Returns:
        The now-active :class:`~atlas.db.models.Profile`.

    Raises:
        ProfileNotFoundError: If no profile has that id.
    """
    profile = get_profile(session, profile_id)
    profile.active = True
    session.add(profile)
    _deactivate_others(session, keep_id=profile_id)
    session.flush()
    return profile


def _deactivate_others(session: Session, *, keep_id: int | None) -> None:
    """Set ``active=False`` on every profile except ``keep_id``.

    ``keep_id`` is the freshly-flushed profile's primary key; every other row is
    deactivated so exactly one profile remains active.
    """
    for other in session.exec(select(Profile).where(Profile.id != keep_id)).all():
        other.active = False
        session.add(other)
