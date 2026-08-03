"""SQLModel table definitions for Atlas's core data model.

This module defines the growing slice of the data model in PROJECT.md §6 — the
single-user record, search profiles, and the versioned master resume — that
Phase 1 features build on. The remaining tables (job postings, applications, …)
land per-feature, each with its own Alembic migration (PROJECT.md §6; the
data-handling rule in ``docs/agent/coding-standards.md``).

Each class is a SQLModel table (``table=True``): one class that is both the
Pydantic model and the SQLAlchemy table (PROJECT.md §13). JSON-shaped columns
(preferences, settings, parsed structure, …) are stored as SQLite ``JSON`` via
an explicit ``sa_column``; their Python types stay precise for callers.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlmodel import JSON, Column, Field, SQLModel

__all__ = ["MasterResume", "Profile", "ResumeBlock", "User"]


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


class MasterResume(SQLModel, table=True):
    """One immutable version of the single master resume (PROJECT.md §5.3, §6).

    Atlas keeps exactly one master resume per user, shared across all profiles,
    but **versioned**: each ingest (``atlas resume set``) or reparse
    (``atlas resume reparse``) that changes content creates a new row with an
    incremented :attr:`version`, never mutating an earlier one. Past tailored
    resumes remember which version they were built from, so keeping versions
    immutable preserves that traceability. The one-master-resume and monotonic
    single-user versioning invariants are enforced by the repository in code, not
    by database constraints (mirroring the :class:`User` / :class:`Profile`
    convention).

    The parsed structure is stored twice, from a single source, so the two never
    drift: the whole-resume snapshot in :attr:`parsed` (a fast structural read)
    and the individual :class:`ResumeBlock` rows (the queryable, content-ID'd
    traceability anchor tailoring and honesty validation trace back to).

    Attributes:
        id: Surrogate primary key (assigned on insert).
        version: 1-based, monotonically increasing version number.
        source_path: The path this version was read from (``atlas resume set``),
            or ``None`` when produced by a reparse of an earlier version.
        raw_markdown: The verbatim Markdown source, kept for reparsing and for
            content-change detection against a later ingest.
        parsed: The parsed structure as a JSON object (a serialized
            :class:`~atlas.resume.structure.ParsedResume`).
        created_at: When this version was created (timezone-aware UTC).
    """

    __tablename__ = "master_resume"

    id: int | None = Field(default=None, primary_key=True)
    version: int
    source_path: str | None = None
    raw_markdown: str
    parsed: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: datetime


class ResumeBlock(SQLModel, table=True):
    """One addressable block of a master-resume version (PROJECT.md §5.3, §6).

    A block is a single structured unit of the resume — a summary paragraph, one
    experience bullet, a skill group, an education entry, and so on. Each carries
    a **stable** :attr:`content_id` (derived from its type and normalized text)
    so an unchanged bullet keeps the same id across versions, letting tailoring
    decisions and the honesty validator trace an output claim back to real source
    content.

    Attributes:
        id: Surrogate primary key (assigned on insert).
        master_resume_id: The owning :class:`MasterResume` version's id.
        type: The block's kind (a :class:`~atlas.resume.structure.BlockType`
            value, stored as its string).
        content_id: A stable identifier for this block's content (see
            :func:`atlas.resume.structure.content_id_for`).
        position: The block's 0-based order within the resume.
        text: The block's text content.
        tags: Optional structured metadata (metrics, tech tags) as a JSON object;
            empty when none was extracted.
    """

    __tablename__ = "resume_block"

    id: int | None = Field(default=None, primary_key=True)
    master_resume_id: int = Field(foreign_key="master_resume.id")
    type: str
    content_id: str
    position: int
    text: str
    tags: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
