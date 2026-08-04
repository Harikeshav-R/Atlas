"""Application-tracking reporting and rendering for the Atlas CLI.

The ``atlas list``, ``atlas apply mark``, and ``atlas status set`` commands
(PROJECT.md §9) keep their Typer wiring thin in :mod:`atlas.cli.main` and delegate
here, mirroring the ``atlas postings`` split (:mod:`atlas.cli.scrape`): this module
holds the **pure, I/O-light logic** — building a serializable view of tracked
applications and rendering it (and a status-change outcome) through the shared
semantic theme — so it is testable against the in-memory ``db_engine`` fixture
without invoking the CLI (AGENTS.md §6.2). The status-transition orchestration
itself lives in :mod:`atlas.tracking.service`, which the commands call within one
:func:`~atlas.db.session.session_scope` transaction.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from pydantic import BaseModel
from rich.table import Table
from rich.text import Text

from atlas.cli.matching import verdict_style
from atlas.db.models import Company, JobPosting
from atlas.matching.repository import get_latest_match_score
from atlas.tracking.repository import list_applications
from atlas.tracking.status import ApplicationStatus

if TYPE_CHECKING:
    from rich.console import RenderableType
    from sqlmodel import Session

    from atlas.tracking.service import StatusChangeOutcome

__all__ = [
    "ApplicationListReport",
    "ApplicationSummary",
    "build_applications_report",
    "render_applications",
    "render_status_change",
    "status_style",
]

#: Semantic theme style for each application status, so the pipeline reads at a
#: glance: in-flight stages are neutral/accented, an offer is green, and a
#: rejection/ghosting reads red — matching the verdict palette in
#: :mod:`atlas.cli.matching`.
_STATUS_STYLES: dict[str, str] = {
    ApplicationStatus.SAVED.value: "muted",
    ApplicationStatus.PREPARING.value: "muted",
    ApplicationStatus.READY.value: "accent",
    ApplicationStatus.APPLIED.value: "accent",
    ApplicationStatus.OA.value: "warning",
    ApplicationStatus.INTERVIEW.value: "warning",
    ApplicationStatus.OFFER.value: "success",
    ApplicationStatus.REJECTED.value: "bad",
    ApplicationStatus.WITHDRAWN.value: "muted",
    ApplicationStatus.GHOSTED.value: "bad",
}


def status_style(status: str) -> str:
    """Return the semantic theme style name for ``status`` (``muted`` if unknown)."""
    return _STATUS_STYLES.get(status, "muted")


class ApplicationSummary(BaseModel):
    """A compact, serializable view of one tracked application (``atlas list``).

    Attributes:
        id: The application's primary key.
        status: The current pipeline stage.
        title: The role title of the posting the application is for.
        company: The hiring company's name.
        score: The posting's latest fit score (0-100), or ``None`` if unscored.
        verdict: The posting's latest fit verdict, or ``None`` if unscored.
        applied_at: When the application was marked applied, if at all.
        updated_at: When the application was last updated.
    """

    id: int
    status: str
    title: str
    company: str
    score: int | None = None
    verdict: str | None = None
    applied_at: datetime | None = None
    updated_at: datetime


class ApplicationListReport(BaseModel):
    """The result of ``atlas list``.

    Attributes:
        applications: One :class:`ApplicationSummary` per matching application,
            most recently updated first.
    """

    applications: list[ApplicationSummary]


def build_applications_report(
    session: Session,
    *,
    status: ApplicationStatus | None = None,
    profile_id: int | None = None,
) -> ApplicationListReport:
    """Build an :class:`ApplicationListReport` from the tracked applications.

    Pure over the session: reads the applications (optionally filtered by stage or
    profile), resolving each posting's title/company and latest fit score for
    display. The status/profile filters map straight onto
    :func:`atlas.tracking.repository.list_applications`.
    """
    summaries: list[ApplicationSummary] = []
    for application in list_applications(session, status=status, profile_id=profile_id):
        assert application.id is not None  # persisted rows always have an id
        posting = session.get(JobPosting, application.job_posting_id)
        assert posting is not None  # a non-null foreign key never misses
        company = session.get(Company, posting.company_id)
        assert company is not None  # a non-null foreign key never misses
        latest = get_latest_match_score(session, application.job_posting_id)
        summaries.append(
            ApplicationSummary(
                id=application.id,
                status=application.status,
                title=posting.title,
                company=company.name,
                score=latest.score if latest is not None else None,
                verdict=latest.verdict if latest is not None else None,
                applied_at=application.applied_at,
                updated_at=application.updated_at,
            )
        )
    return ApplicationListReport(applications=summaries)


def render_applications(report: ApplicationListReport) -> RenderableType:
    """Render an :class:`ApplicationListReport` as a styled Rich renderable.

    Produces a table of applications (id, status, title, company, fit, applied
    date) using the shared semantic theme. An empty report renders a muted hint
    pointing at ``atlas tailor``. Machine-readable output is produced separately
    via :meth:`ApplicationListReport.model_dump_json`.
    """
    if not report.applications:
        return Text("No applications yet — run `atlas tailor <job_id>`.", style="muted")
    table = Table(title="Applications", title_style="heading", title_justify="left")
    table.add_column("ID", justify="right", no_wrap=True)
    table.add_column("Status", no_wrap=True)
    table.add_column("Title", style="accent")
    table.add_column("Company")
    table.add_column("Fit", no_wrap=True)
    table.add_column("Applied", no_wrap=True)
    for application in report.applications:
        table.add_row(
            str(application.id),
            Text(application.status, style=status_style(application.status)),
            application.title,
            application.company,
            _fit_text(application.score, application.verdict),
            _date_text(application.applied_at),
        )
    return table


def render_status_change(outcome: StatusChangeOutcome) -> RenderableType:
    """Render a :class:`~atlas.tracking.service.StatusChangeOutcome` as a Rich grid.

    Shows the application id, the ``previous → new`` stage move (styled through the
    status palette), whether it was forced, and — where set — the recorded applied
    date, final outcome, and advisory deadline.
    """
    move = Text.assemble(
        (outcome.previous_status, status_style(outcome.previous_status)),
        (" → ", "muted"),
        (outcome.new_status, status_style(outcome.new_status)),
    )
    grid = Table.grid(padding=(0, 2))
    grid.add_column(style="muted", no_wrap=True)
    grid.add_column()
    grid.add_row("Application", str(outcome.application_id))
    grid.add_row("Status", move)
    if outcome.forced:
        grid.add_row("Forced", Text("yes", style="warning"))
    if outcome.applied_at is not None:
        grid.add_row("Applied", _date_text(outcome.applied_at))
    if outcome.outcome is not None:
        grid.add_row("Outcome", Text(outcome.outcome, style=status_style(outcome.outcome)))
    if outcome.due is not None:
        grid.add_row("Due", _date_text(outcome.due))
    return grid


def _fit_text(score: int | None, verdict: str | None) -> Text:
    """Render an application's posting fit as ``"<score> <verdict>"``, or ``"—"``."""
    if score is None or verdict is None:
        return Text("—", style="muted")
    return Text.assemble((f"{score} ", "accent"), (verdict, verdict_style(verdict)))


def _date_text(value: datetime | None) -> Text:
    """Render a date as ``YYYY-MM-DD``, or a muted ``"—"`` when absent."""
    if value is None:
        return Text("—", style="muted")
    return Text(value.date().isoformat(), style="muted")
