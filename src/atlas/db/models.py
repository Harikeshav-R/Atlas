"""SQLModel table definitions for Atlas's core data model.

This module defines the growing slice of the data model in PROJECT.md §6 — the
single-user record, search profiles, the versioned master resume, and scraped
job postings (with their company and source) — that Phase 1 features build on.
The remaining tables (match scores, applications, …) land per-feature, each with
its own Alembic migration (PROJECT.md §6; the data-handling rule in
``docs/agent/coding-standards.md``).

Each class is a SQLModel table (``table=True``): one class that is both the
Pydantic model and the SQLAlchemy table (PROJECT.md §13). JSON-shaped columns
(preferences, settings, parsed structure, …) are stored as SQLite ``JSON`` via
an explicit ``sa_column``; their Python types stay precise for callers.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlmodel import JSON, Column, Field, SQLModel

from atlas.db.types import UtcDateTime

__all__ = [
    "Application",
    "Company",
    "JobPosting",
    "JobSource",
    "MasterResume",
    "MatchScore",
    "Profile",
    "ResumeBlock",
    "TailoredResume",
    "User",
]


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
    created_at: datetime = Field(sa_column=Column(UtcDateTime, nullable=False))


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


class Company(SQLModel, table=True):
    """A company a job posting belongs to (PROJECT.md §6).

    Populated from a scraped posting's company name today; the ATS fields
    (:attr:`ats_type`, :attr:`ats_board_ref`) stay empty until the Phase 2
    watchlist feature auto-detects a company's board. Deduplicated by name in the
    repository (in code, not by a DB constraint), so re-adding a posting for the
    same company reuses its row.

    Attributes:
        id: Surrogate primary key (assigned on insert).
        name: The company's display name.
        ats_type: The company's ATS provider (e.g. ``"greenhouse"``), if known.
        ats_board_ref: The company's board URL/token on that ATS, if known.
        domain: The company's primary web domain, if known.
        notes: Free-form user notes about the company.
    """

    __tablename__ = "company"

    id: int | None = Field(default=None, primary_key=True)
    name: str
    ats_type: str | None = None
    ats_board_ref: str | None = None
    domain: str | None = None
    notes: str | None = None


class JobSource(SQLModel, table=True):
    """Where a job posting came from (PROJECT.md §5.4, §6).

    A source is an ATS board, an aggregator search, a pasted URL, or a scrape.
    The paste-URL flow (PROJECT.md §5.5) uses a single ``type="url"`` row,
    reused for every pasted posting; the ATS/aggregator source rows arrive with
    the Phase 2 discovery daemon.

    Attributes:
        id: Surrogate primary key (assigned on insert).
        type: The source kind — ``"ats"`` / ``"aggregator"`` / ``"url"`` /
            ``"scrape"``.
        config: Source-specific settings as a JSON object (empty for a pasted
            URL); ATS/aggregator sources store their board ref, saved search, etc.
        profile_id: The owning profile, if the source is profile-scoped; ``None``
            for the shared paste-URL source.
        enabled: Whether a poller should include this source (Phase 2).
        last_polled_at: When this source was last polled, or ``None`` if never
            (timezone-aware UTC).
    """

    __tablename__ = "job_source"

    id: int | None = Field(default=None, primary_key=True)
    type: str
    config: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    profile_id: int | None = Field(default=None, foreign_key="profile.id")
    enabled: bool = True
    last_polled_at: datetime | None = Field(default=None, sa_column=Column(UtcDateTime))


class JobPosting(SQLModel, table=True):
    """A normalized job posting scraped from a URL (PROJECT.md §5.5, §6).

    Holds the normalized fields extracted from a posting — structured data first
    (JSON-LD / OpenGraph), then an AI extraction pass over the page text
    (:mod:`atlas.scrape`). The raw HTML lives on disk under the data dir and is
    referenced by :attr:`raw_snapshot_ref` (never stored as a DB blob, PROJECT.md
    §6), so a posting can be re-parsed without re-fetching. Deduplicated by
    :attr:`dedupe_hash` (the normalized apply URL) so re-adding the same posting
    is a no-op.

    Attributes:
        id: Surrogate primary key (assigned on insert).
        external_id: The source's own id for the posting, if any.
        source_id: The owning :class:`JobSource`'s id.
        company_id: The owning :class:`Company`'s id.
        title: The role title.
        location: The posting's location(s), as free text.
        remote_type: On-site / hybrid / remote, if determinable.
        employment_type: Full-time / contract / internship, if determinable.
        seniority: The role's seniority, if determinable.
        salary: Salary details as a JSON object (empty when not stated).
        description: The full description text.
        requirements: Requirements as a JSON object (e.g. ``must`` / ``nice``).
        keywords: Tech stack / keywords, as a JSON array.
        apply_url: The URL to apply at (the pasted URL for a paste-URL posting).
        posted_at: When the role was posted, if known (timezone-aware UTC).
        raw_snapshot_ref: On-disk path to the raw HTML snapshot, or ``None``.
        fetched_at: When Atlas fetched the posting (timezone-aware UTC).
        dedupe_hash: A stable hash used to collapse duplicate postings.
    """

    __tablename__ = "job_posting"

    id: int | None = Field(default=None, primary_key=True)
    external_id: str | None = None
    source_id: int = Field(foreign_key="job_source.id")
    company_id: int = Field(foreign_key="company.id")
    title: str
    location: str | None = None
    remote_type: str | None = None
    employment_type: str | None = None
    seniority: str | None = None
    salary: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    description: str = ""
    requirements: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    keywords: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    apply_url: str
    posted_at: datetime | None = Field(default=None, sa_column=Column(UtcDateTime))
    raw_snapshot_ref: str | None = None
    fetched_at: datetime = Field(sa_column=Column(UtcDateTime, nullable=False))
    dedupe_hash: str


class MatchScore(SQLModel, table=True):
    """One AI fit assessment of a posting against a profile (PROJECT.md §5.6, §6).

    Atlas scores every candidate posting for fit rather than pre-filtering it away
    (PROJECT.md §5.6): the AI returns a 0-100 :attr:`score`, a :attr:`verdict`, a
    short :attr:`rationale`, and the matched strengths / gaps / dealbreaker hits it
    found, while Atlas computes deterministic :attr:`signals` (salary / location /
    work-auth / deal-breakers) that inform and annotate the score without
    discarding anything.

    Scores are **append-only**: re-scoring a posting (``atlas score``) inserts a
    new row rather than mutating an earlier one, mirroring the immutable versioning
    of :class:`MasterResume`, so the history of how a posting's fit changed (across
    prompt/model versions or profile edits) is preserved. The latest row by
    :attr:`created_at` is the one surfaced in the queue.

    Beyond the PROJECT.md §6 column list this row also persists :attr:`salary_fit`
    (the AI's salary verdict) and :attr:`signals` (the computed deterministic
    signals) so the badges render on re-view without recomputing against a
    since-changed profile.

    Attributes:
        id: Surrogate primary key (assigned on insert).
        job_posting_id: The scored :class:`JobPosting`'s id.
        profile_id: The :class:`Profile` the posting was scored against.
        score: The AI fit score, 0-100.
        verdict: The AI verdict — ``strong`` / ``good`` / ``stretch`` / ``weak``.
        rationale: A 2-4 sentence explanation of the score.
        matched_strengths: Strengths the posting matches, as a JSON array.
        gaps: Missing keywords/skills/requirements, as a JSON array.
        dealbreaker_hits: Deal-breakers the posting triggers, as a JSON array.
        salary_fit: The AI salary verdict — ``above`` / ``within`` / ``below`` /
            ``unknown``.
        signals: The computed deterministic signals as a JSON object (salary /
            location / work-auth / deal-breakers), shown as badges.
        model: The AI model that produced the assessment.
        created_at: When this assessment was created (timezone-aware UTC).
    """

    __tablename__ = "match_score"

    id: int | None = Field(default=None, primary_key=True)
    job_posting_id: int = Field(foreign_key="job_posting.id")
    profile_id: int = Field(foreign_key="profile.id")
    score: int
    verdict: str
    rationale: str
    matched_strengths: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    gaps: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    dealbreaker_hits: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    salary_fit: str
    signals: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    model: str
    created_at: datetime = Field(sa_column=Column(UtcDateTime, nullable=False))


class Application(SQLModel, table=True):
    """A job application Atlas is preparing or tracking (PROJECT.md §5.12, §6).

    Every posting the user prepares materials for becomes an ``Application`` — the
    parent that a :class:`TailoredResume` (and, later, a cover letter and Q&A
    answers) hangs off. This table lands with resume tailoring (a tailored resume
    needs an application to belong to); the full status **state machine** and the
    Kanban/TUI that drive :attr:`status` / :attr:`status_history` / :attr:`applied_at`
    / :attr:`outcome` arrive with application tracking (PROJECT.md §5.12). The
    columns are the complete §6 set so that later work needs no further migration.
    An application is deduplicated by (job posting, profile) in code.

    Attributes:
        id: Surrogate primary key (assigned on insert).
        job_posting_id: The :class:`JobPosting` this application is for.
        profile_id: The :class:`Profile` the application is being prepared under.
        status: The current pipeline stage (defaults to ``"preparing"``; the full
            state machine is wired in a later feature).
        status_history: Timestamped status transitions, as a JSON array (empty
            until the state machine lands).
        applied_at: When the user marked the application submitted, if at all
            (timezone-aware UTC).
        outcome: The final outcome (offer / rejected / …), if known.
        notes: Free-form user notes / journal.
        created_at: When the application was created (timezone-aware UTC).
        updated_at: When the application was last updated (timezone-aware UTC).
    """

    __tablename__ = "application"

    id: int | None = Field(default=None, primary_key=True)
    job_posting_id: int = Field(foreign_key="job_posting.id")
    profile_id: int = Field(foreign_key="profile.id")
    status: str = "preparing"
    status_history: list[dict[str, Any]] = Field(default_factory=list, sa_column=Column(JSON))
    applied_at: datetime | None = Field(default=None, sa_column=Column(UtcDateTime))
    outcome: str | None = None
    notes: str | None = None
    created_at: datetime = Field(sa_column=Column(UtcDateTime, nullable=False))
    updated_at: datetime = Field(sa_column=Column(UtcDateTime, nullable=False))


class TailoredResume(SQLModel, table=True):
    """One tailored resume produced for an application (PROJECT.md §5.7, §6).

    A tailored resume selects and rewords content from a specific immutable
    :class:`MasterResume` version (:attr:`master_resume_version`, the traceability
    anchor) to fit one posting, and is rendered to a one-page PDF referenced by
    :attr:`rendered_pdf_ref` (on disk, never a DB blob, §6). Tailored resumes are
    **append-only and versioned per application**: re-tailoring inserts a new row
    with an incremented :attr:`version` rather than mutating an earlier one.

    Attributes:
        id: Surrogate primary key (assigned on insert).
        application_id: The owning :class:`Application`.
        master_resume_version: The master-resume version the content was drawn
            from (links back to the immutable source for traceability).
        selections: The selected, content-ID'd items and their reasons, as a JSON
            array.
        final_content: The rendered resume view model snapshot, as a JSON object.
        rendered_pdf_ref: On-disk path to the rendered PDF, or ``None``.
        decisions: The include/exclude/reword rationale per item, as a JSON array.
        edited_by_user: Whether the user has hand-edited this tailored resume.
        version: 1-based version number within the owning application.
        created_at: When this tailored resume was created (timezone-aware UTC).
    """

    __tablename__ = "tailored_resume"

    id: int | None = Field(default=None, primary_key=True)
    application_id: int = Field(foreign_key="application.id")
    master_resume_version: int
    selections: list[dict[str, Any]] = Field(default_factory=list, sa_column=Column(JSON))
    final_content: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    rendered_pdf_ref: str | None = None
    decisions: list[dict[str, Any]] = Field(default_factory=list, sa_column=Column(JSON))
    edited_by_user: bool = False
    version: int
    created_at: datetime = Field(sa_column=Column(UtcDateTime, nullable=False))
