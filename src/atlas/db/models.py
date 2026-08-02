"""SQLModel table definitions for Atlas's core data model.

This module defines the **foundational slice** of the data model in PROJECT.md
§6 — the single-user record and search profiles — that later Phase 1 features
build on. The remaining tables (master resume, job postings, applications, …)
land per-feature, each with its own Alembic migration (PROJECT.md §6; the
data-handling rule in ``docs/agent/coding-standards.md``).

Each class is a SQLModel table (``table=True``): one class that is both the
Pydantic model and the SQLAlchemy table (PROJECT.md §13). JSON-shaped columns
(preferences, settings, …) are stored as SQLite ``JSON`` via an explicit
``sa_column``; their Python types stay precise for callers.
"""

from __future__ import annotations

from typing import Any

from sqlmodel import JSON, Column, Field, SQLModel

__all__ = ["Profile", "User"]


class User(SQLModel, table=True):
    """The single Atlas user (name, contact, and global settings).

    Atlas is single-user (PROJECT.md §6); the one-row convention is enforced by
    the onboarding flow in Phase 1, not by a database constraint here.

    Attributes:
        id: Surrogate primary key (assigned on insert).
        name: The user's display name.
        email: The user's contact email, if provided.
        settings: Global, free-form settings as a JSON object.
    """

    id: int | None = Field(default=None, primary_key=True)
    name: str
    email: str | None = None
    settings: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))


class Profile(SQLModel, table=True):
    """A search profile: preferences and tailoring emphasis for one job hunt.

    Profiles share the single master resume and differ only in preferences,
    match criteria, and tailoring emphasis (PROJECT.md §5.2, §5.3).

    Attributes:
        id: Surrogate primary key (assigned on insert).
        name: The profile's display name (e.g. ``"Backend Engineer"``).
        preferences: Captured job-search preferences as a JSON object.
        tailoring_emphasis: Themes to foreground when tailoring, as a JSON array.
        match_criteria: Structured criteria fed to fit scoring, as a JSON object.
        active: Whether this profile is currently active.
    """

    id: int | None = Field(default=None, primary_key=True)
    name: str
    preferences: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    tailoring_emphasis: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    match_criteria: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    active: bool = True
