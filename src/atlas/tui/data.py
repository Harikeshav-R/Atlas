"""Pure view-model builders for the Atlas TUI (PROJECT.md §8).

The Textual screens (:mod:`atlas.tui.screens`) stay a thin presentation layer:
every bit of data logic lives here, as **pure functions over an open**
:class:`~sqlmodel.Session` returning serializable Pydantic models — so it is
testable against the in-memory ``db_engine`` fixture with no Textual/`Pilot` in
the loop (AGENTS.md §6.2), the same split the CLI uses (`build_*` in
:mod:`atlas.cli.tracking` / :mod:`atlas.cli.scrape`).

Two screens reuse the CLI builders directly and need nothing here:
- Applications (table + Kanban) → :func:`atlas.cli.tracking.build_applications_report`.
- Posting detail → :func:`atlas.cli.scrape.build_posting_detail`.

This module adds the two the CLI lacks: the **Dashboard** report (a pipeline
funnel + active profile + recent activity + upcoming deadlines) and the
**Application detail** report (status timeline + latest materials + fit).
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from pydantic import BaseModel

from atlas.coverletter.repository import get_latest_cover_letter
from atlas.db.models import Company, JobPosting, JobSource
from atlas.matching.repository import get_latest_match_score, list_scored_postings
from atlas.profiles.repository import get_active_profile
from atlas.resume.repository import get_blocks, get_latest_master_resume
from atlas.tailor.repository import get_application, get_latest_tailored_resume
from atlas.tailor.structure import TailoredItem
from atlas.tracking.repository import count_applications_by_status, list_applications
from atlas.tracking.status import ApplicationStatus

if TYPE_CHECKING:
    from sqlmodel import Session

__all__ = [
    "ApplicationDetail",
    "DashboardReport",
    "DeadlineEntry",
    "DiscoverQueue",
    "DiscoverRow",
    "MaterialSummary",
    "RecentApplication",
    "ResumeBlockView",
    "StatusCount",
    "TailorWorkspaceView",
    "TailoredSelection",
    "TimelineEntry",
    "build_application_detail",
    "build_dashboard_report",
    "build_discover_queue",
    "build_tailor_workspace",
]


class StatusCount(BaseModel):
    """One bar of the Dashboard pipeline funnel.

    Attributes:
        status: The pipeline stage.
        count: How many applications are currently in it.
    """

    status: str
    count: int


class RecentApplication(BaseModel):
    """A recently-updated application, for the Dashboard activity list.

    Attributes:
        id: The application's id.
        title: The posting's role title.
        company: The hiring company's name.
        status: The application's current stage.
        updated_at: When it was last updated.
    """

    id: int
    title: str
    company: str
    status: str
    updated_at: datetime


class DeadlineEntry(BaseModel):
    """An upcoming deadline recorded on an application's status history.

    Deadlines live only inside ``status_history[].due`` (there is no ``due``
    column); the Dashboard surfaces the latest such date per application.

    Attributes:
        application_id: The application the deadline belongs to.
        title: The posting's role title.
        company: The hiring company's name.
        status: The application's current stage.
        due: The advisory deadline.
    """

    application_id: int
    title: str
    company: str
    status: str
    due: datetime


class DashboardReport(BaseModel):
    """The Dashboard screen's view model (PROJECT.md §8).

    Attributes:
        active_profile: The active profile's name, or ``None`` if none is active.
        total_applications: How many applications exist in total.
        funnel: The pipeline funnel — one :class:`StatusCount` per stage, in the
            canonical :class:`~atlas.tracking.status.ApplicationStatus` order
            (stages with no applications show a zero count).
        recent: The most recently-updated applications (newest first, capped).
        deadlines: Upcoming deadlines, soonest first.
    """

    active_profile: str | None
    total_applications: int
    funnel: list[StatusCount]
    recent: list[RecentApplication]
    deadlines: list[DeadlineEntry]


class TimelineEntry(BaseModel):
    """One entry in an application's status timeline (a ``status_history`` row).

    Attributes:
        from_status: The stage before the transition.
        to_status: The stage after it.
        at: When the transition happened.
        forced: Whether it bypassed the state machine.
        due: An advisory deadline recorded with the transition, if any.
        note: A free-form note recorded with the transition, if any.
    """

    from_status: str
    to_status: str
    at: datetime
    forced: bool = False
    due: datetime | None = None
    note: str | None = None


class MaterialSummary(BaseModel):
    """A compact view of one prepared material (tailored resume or cover letter).

    Attributes:
        version: The material's 1-based version.
        path: The rendered PDF path, or ``None`` if it was not rendered.
    """

    version: int
    path: str | None


class ApplicationDetail(BaseModel):
    """The Application-detail screen's view model (PROJECT.md §8).

    Attributes:
        id: The application's id.
        title: The posting's role title.
        company: The hiring company's name.
        status: The current stage.
        applied_at: When the application was marked applied, if at all.
        outcome: The final outcome, if a terminal stage was reached.
        notes: Free-form user notes.
        score: The posting's latest fit score, or ``None`` if unscored.
        verdict: The posting's latest fit verdict, or ``None`` if unscored.
        tailored_resume: The latest tailored resume, or ``None`` if none exists.
        cover_letter: The latest cover letter, or ``None`` if none exists.
        timeline: The status history, oldest first.
    """

    id: int
    title: str
    company: str
    status: str
    applied_at: datetime | None
    outcome: str | None
    notes: str | None
    score: int | None
    verdict: str | None
    tailored_resume: MaterialSummary | None
    cover_letter: MaterialSummary | None
    timeline: list[TimelineEntry]


def _posting_and_company(session: Session, job_posting_id: int) -> tuple[JobPosting, str]:
    """Return a posting and its company name (both non-null foreign keys)."""
    posting = session.get(JobPosting, job_posting_id)
    assert posting is not None  # a non-null foreign key never misses
    company = session.get(Company, posting.company_id)
    assert company is not None  # a non-null foreign key never misses
    return posting, company.name


def build_dashboard_report(session: Session, *, recent_limit: int = 5) -> DashboardReport:
    """Build the :class:`DashboardReport` from the tracked applications.

    Pure over the session: the funnel comes from
    :func:`atlas.tracking.repository.count_applications_by_status` (padded to the
    full status set in canonical order), the active profile from
    :func:`atlas.profiles.repository.get_active_profile`, and recent activity /
    deadlines from :func:`atlas.tracking.repository.list_applications` (already
    newest-updated first). Deadlines are scanned out of each application's
    ``status_history`` (the latest ``due`` per application) and sorted soonest
    first.

    Args:
        session: The open session to read within.
        recent_limit: How many recently-updated applications to include.
    """
    counts = count_applications_by_status(session)
    funnel = [
        StatusCount(status=status.value, count=counts.get(status.value, 0))
        for status in ApplicationStatus
    ]

    profile = get_active_profile(session)
    applications = list(list_applications(session))

    recent: list[RecentApplication] = []
    deadlines: list[DeadlineEntry] = []
    for application in applications:
        assert application.id is not None  # persisted rows always have an id
        posting, company = _posting_and_company(session, application.job_posting_id)
        if len(recent) < recent_limit:
            recent.append(
                RecentApplication(
                    id=application.id,
                    title=posting.title,
                    company=company,
                    status=application.status,
                    updated_at=application.updated_at,
                )
            )
        due = _latest_due(application.status_history)
        if due is not None:
            deadlines.append(
                DeadlineEntry(
                    application_id=application.id,
                    title=posting.title,
                    company=company,
                    status=application.status,
                    due=due,
                )
            )

    deadlines.sort(key=lambda entry: entry.due)
    return DashboardReport(
        active_profile=profile.name if profile is not None else None,
        total_applications=len(applications),
        funnel=funnel,
        recent=recent,
        deadlines=deadlines,
    )


def build_application_detail(session: Session, application_id: int) -> ApplicationDetail:
    """Build the :class:`ApplicationDetail` for one application.

    Wraps :func:`atlas.tailor.repository.get_application`,
    :func:`atlas.tailor.repository.get_latest_tailored_resume`,
    :func:`atlas.coverletter.repository.get_latest_cover_letter`, and
    :func:`atlas.matching.repository.get_latest_match_score` (keyed on the
    application's posting **and its profile**, so the fit shown is the one this
    application was prepared under), and decodes the ``status_history`` JSON into a
    typed timeline (oldest first).

    Raises:
        ApplicationNotFoundError: If no application has ``application_id``.
    """
    application = get_application(session, application_id)
    assert application.id is not None  # persisted rows always have an id
    posting, company = _posting_and_company(session, application.job_posting_id)

    latest_score = get_latest_match_score(
        session, application.job_posting_id, profile_id=application.profile_id
    )
    tailored = get_latest_tailored_resume(session, application.id)
    letter = get_latest_cover_letter(session, application.id)

    timeline = [TimelineEntry.model_validate(entry) for entry in application.status_history]

    return ApplicationDetail(
        id=application.id,
        title=posting.title,
        company=company,
        status=application.status,
        applied_at=application.applied_at,
        outcome=application.outcome,
        notes=application.notes,
        score=latest_score.score if latest_score is not None else None,
        verdict=latest_score.verdict if latest_score is not None else None,
        tailored_resume=(
            MaterialSummary(version=tailored.version, path=tailored.rendered_pdf_ref)
            if tailored is not None
            else None
        ),
        cover_letter=(
            MaterialSummary(version=letter.version, path=letter.rendered_pdf_ref)
            if letter is not None
            else None
        ),
        timeline=timeline,
    )


def _latest_due(status_history: list[dict[str, object]]) -> datetime | None:
    """Return the most recent ``due`` recorded across status-history entries.

    History is append-only, so the last entry carrying a ``due`` is the current
    advisory deadline. Entries without a ``due`` are ignored.
    """
    latest: datetime | None = None
    for entry in status_history:
        parsed = TimelineEntry.model_validate(entry)
        if parsed.due is not None:
            latest = parsed.due
    return latest


class ResumeBlockView(BaseModel):
    """One master-resume block, for the Tailor workspace's master-resume pane.

    Attributes:
        content_id: The stable content id (the join key to a tailored selection).
        type: The block type (experience / project / skill / …).
        text: The block's text.
    """

    content_id: str
    type: str
    text: str


class TailoredSelection(BaseModel):
    """One selected/reworded item from the latest tailored resume.

    Attributes:
        content_id: The source block's content id.
        included: Whether the item appears in the tailored resume.
        reason: Why it was selected/reworded.
        final_text: The tailored text.
    """

    content_id: str
    included: bool
    reason: str
    final_text: str


class TailorWorkspaceView(BaseModel):
    """The Tailor-workspace screen's view model (PROJECT.md §8, screen #4).

    Attributes:
        application_id: The application being worked on.
        job_posting_id: The posting the application is for (fed to the AI actions).
        title: The posting's role title.
        company: The hiring company's name.
        master_blocks: The latest master-resume blocks (the source content).
        selections: The latest tailored-resume selections, or empty if none yet.
        resume_version: The latest tailored-resume version, or ``None`` if none yet.
        resume_path: The latest tailored-resume PDF path, or ``None``.
        cover_version: The latest cover-letter version, or ``None`` if none yet.
        cover_path: The latest cover-letter PDF path, or ``None``.
    """

    application_id: int
    job_posting_id: int
    title: str
    company: str
    master_blocks: list[ResumeBlockView]
    selections: list[TailoredSelection]
    resume_version: int | None
    resume_path: str | None
    cover_version: int | None
    cover_path: str | None


def build_tailor_workspace(session: Session, application_id: int) -> TailorWorkspaceView:
    """Build the :class:`TailorWorkspaceView` for one application.

    Pure over the session: resolves the application (raising if unknown) and its
    posting, reads the latest master-resume blocks
    (:func:`atlas.resume.repository.get_latest_master_resume` +
    :func:`~atlas.resume.repository.get_blocks`), and decodes the latest tailored
    resume's ``selections`` into typed :class:`TailoredSelection` items plus the
    latest cover letter's version/path — the material the workspace displays and
    the ``job_posting_id`` its AI actions target.

    Raises:
        ApplicationNotFoundError: If no application has ``application_id``.
    """
    application = get_application(session, application_id)
    assert application.id is not None  # persisted rows always have an id
    posting, company = _posting_and_company(session, application.job_posting_id)

    master = get_latest_master_resume(session)
    master_blocks: list[ResumeBlockView] = []
    if master is not None:
        assert master.id is not None  # persisted rows always have an id
        master_blocks = [
            ResumeBlockView(content_id=block.content_id, type=block.type, text=block.text)
            for block in get_blocks(session, master.id)
        ]

    tailored = get_latest_tailored_resume(session, application.id)
    selections: list[TailoredSelection] = []
    if tailored is not None:
        for raw in tailored.selections:
            item = TailoredItem.model_validate(raw)
            selections.append(
                TailoredSelection(
                    content_id=item.content_id,
                    included=item.included,
                    reason=item.reason,
                    final_text=item.final_text,
                )
            )

    letter = get_latest_cover_letter(session, application.id)

    return TailorWorkspaceView(
        application_id=application.id,
        job_posting_id=application.job_posting_id,
        title=posting.title,
        company=company,
        master_blocks=master_blocks,
        selections=selections,
        resume_version=tailored.version if tailored is not None else None,
        resume_path=tailored.rendered_pdf_ref if tailored is not None else None,
        cover_version=letter.version if letter is not None else None,
        cover_path=letter.rendered_pdf_ref if letter is not None else None,
    )


class DiscoverRow(BaseModel):
    """One row of the Discover queue — a scored posting (PROJECT.md §8, screen #2).

    Attributes:
        id: The posting's id (the key the row's actions target).
        title: The role title.
        company: The hiring company's name.
        location: The posting's location, if any.
        salary: A display string for the stated compensation (``"—"`` when none).
        source: Where the posting came from (the job source's type).
        score: The latest fit score (0-100).
        verdict: The latest fit verdict.
        rationale: The AI's short explanation of the score (shown in the detail pane).
        queue_status: The posting's triage state (``new`` / ``saved``).
    """

    id: int
    title: str
    company: str
    location: str | None
    salary: str
    source: str
    score: int
    verdict: str
    rationale: str
    queue_status: str


class DiscoverQueue(BaseModel):
    """The Discover screen's view model: the ranked scored-posting queue.

    Attributes:
        rows: One :class:`DiscoverRow` per scored, non-dismissed posting, ranked by
            fit (highest score first).
    """

    rows: list[DiscoverRow]


def _salary_display(salary: dict[str, object]) -> str:
    """Render a posting's ``salary`` JSON as a compact display string.

    Uses ``min`` / ``max`` / ``currency`` when present, in any combination; returns
    a muted ``"—"`` when the posting stated no compensation.
    """
    low = salary.get("min")
    high = salary.get("max")
    currency = salary.get("currency")
    if low is None and high is None:
        return "—"
    if low is not None and high is not None:
        amount = f"{low} - {high}"
    else:
        amount = str(low if low is not None else high)
    return f"{amount} {currency}" if currency is not None else amount


def build_discover_queue(session: Session) -> DiscoverQueue:
    """Build the :class:`DiscoverQueue` for the active profile's ranked scores.

    Pure over the session: maps
    :func:`atlas.matching.repository.list_scored_postings` for the **active
    profile** (already ranked by fit, excluding dismissed) into rows, resolving each
    posting's company name, its source type, and a salary display string. With no
    active profile the queue is empty.
    """
    profile = get_active_profile(session)
    if profile is None or profile.id is None:
        return DiscoverQueue(rows=[])
    rows: list[DiscoverRow] = []
    for posting, score in list_scored_postings(session, profile.id):
        assert posting.id is not None  # persisted rows always have an id
        company = session.get(Company, posting.company_id)
        assert company is not None  # a non-null foreign key never misses
        source = session.get(JobSource, posting.source_id)
        assert source is not None  # a non-null foreign key never misses
        rows.append(
            DiscoverRow(
                id=posting.id,
                title=posting.title,
                company=company.name,
                location=posting.location,
                salary=_salary_display(posting.salary),
                source=source.type,
                score=score.score,
                verdict=score.verdict,
                rationale=score.rationale,
                queue_status=posting.queue_status,
            )
        )
    return DiscoverQueue(rows=rows)
