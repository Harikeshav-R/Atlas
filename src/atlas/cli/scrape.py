"""Job-posting reporting and rendering for the Atlas CLI.

The ``atlas add`` and ``atlas postings`` commands (PROJECT.md §9) keep their Typer
wiring thin in :mod:`atlas.cli.main` and delegate here, mirroring the
``atlas resume`` split (:mod:`atlas.cli.resume`): this module holds the **pure,
I/O-light logic** — building serializable views of stored postings and rendering
them through the shared semantic theme — so it is testable against the in-memory
``db_engine`` fixture without invoking the CLI (AGENTS.md §6.2). The scrape/persist
orchestration itself lives in :func:`atlas.scrape.service.add_posting`, which the
command calls within one :func:`~atlas.db.session.session_scope` transaction.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel
from rich.console import Group
from rich.table import Table
from rich.text import Text

from atlas.db.models import Company
from atlas.scrape.repository import get_posting, list_postings

if TYPE_CHECKING:
    from rich.console import RenderableType
    from sqlmodel import Session

__all__ = [
    "PostingDetail",
    "PostingSummary",
    "PostingsReport",
    "build_posting_detail",
    "build_postings_report",
    "render_posting_detail",
    "render_postings",
]


class PostingSummary(BaseModel):
    """A compact, serializable view of one stored posting (``atlas postings list``).

    Attributes:
        id: The posting's primary key.
        title: The role title.
        company: The hiring company's name.
        location: The posting's location, if any.
        apply_url: The URL to apply at.
    """

    id: int
    title: str
    company: str
    location: str | None
    apply_url: str


class PostingsReport(BaseModel):
    """The result of ``atlas postings list``.

    Attributes:
        postings: One :class:`PostingSummary` per stored posting, in insertion
            order.
    """

    postings: list[PostingSummary]


class PostingDetail(BaseModel):
    """A full, serializable view of one posting (``atlas postings show``).

    Attributes:
        id: The posting's primary key.
        title: The role title.
        company: The hiring company's name.
        location: The posting's location, if any.
        remote_type: On-site / hybrid / remote, if determinable.
        employment_type: Employment type, if determinable.
        seniority: The role's seniority, if determinable.
        keywords: Tech stack / keywords.
        apply_url: The URL to apply at.
        description: The full description text.
    """

    id: int
    title: str
    company: str
    location: str | None
    remote_type: str | None
    employment_type: str | None
    seniority: str | None
    keywords: list[str]
    apply_url: str
    description: str


def _company_name(session: Session, company_id: int) -> str:
    """Return the name of a posting's company.

    A posting always references an existing company (a non-null foreign key), so
    the lookup never misses.
    """
    company = session.get(Company, company_id)
    assert company is not None
    return company.name


def build_postings_report(session: Session) -> PostingsReport:
    """Build a :class:`PostingsReport` from every stored posting.

    Pure over the session: reads the postings and maps each into a
    :class:`PostingSummary`, resolving the company name for display.
    """
    summaries: list[PostingSummary] = []
    for posting in list_postings(session):
        assert posting.id is not None  # persisted rows always have an id
        summaries.append(
            PostingSummary(
                id=posting.id,
                title=posting.title,
                company=_company_name(session, posting.company_id),
                location=posting.location,
                apply_url=posting.apply_url,
            )
        )
    return PostingsReport(postings=summaries)


def build_posting_detail(session: Session, posting_id: int) -> PostingDetail:
    """Build a :class:`PostingDetail` for one posting.

    Raises:
        JobPostingNotFoundError: If no posting has ``posting_id``.
    """
    posting = get_posting(session, posting_id)
    assert posting.id is not None
    return PostingDetail(
        id=posting.id,
        title=posting.title,
        company=_company_name(session, posting.company_id),
        location=posting.location,
        remote_type=posting.remote_type,
        employment_type=posting.employment_type,
        seniority=posting.seniority,
        keywords=list(posting.keywords),
        apply_url=posting.apply_url,
        description=posting.description,
    )


def render_postings(report: PostingsReport) -> RenderableType:
    """Render a :class:`PostingsReport` as a styled Rich renderable.

    Produces a table of postings (id, title, company, location, apply URL) using
    the shared semantic theme. An empty report renders a muted hint pointing at
    ``atlas add``. Machine-readable output is produced separately via
    :meth:`PostingsReport.model_dump_json`.
    """
    if not report.postings:
        return Text("No postings yet — run `atlas add <url>`.", style="muted")
    table = Table(title="Job postings", title_style="heading", title_justify="left")
    table.add_column("ID", justify="right", no_wrap=True)
    table.add_column("Title", style="accent")
    table.add_column("Company")
    table.add_column("Location")
    table.add_column("Apply URL", style="muted")
    for posting in report.postings:
        table.add_row(
            str(posting.id),
            posting.title,
            posting.company,
            Text(posting.location or "—", style="muted"),
            posting.apply_url,
        )
    return table


def render_posting_detail(detail: PostingDetail) -> RenderableType:
    """Render a :class:`PostingDetail` as a styled Rich renderable."""
    header = Text.assemble(
        (f"{detail.title}", "heading"),
        ("  ", ""),
        (f"@ {detail.company}", "accent"),
    )
    table = Table.grid(padding=(0, 2))
    table.add_column(style="muted", no_wrap=True)
    table.add_column()
    table.add_row("ID", str(detail.id))
    table.add_row("Location", detail.location or "—")
    table.add_row("Remote", detail.remote_type or "—")
    table.add_row("Employment", detail.employment_type or "—")
    table.add_row("Seniority", detail.seniority or "—")
    table.add_row("Keywords", ", ".join(detail.keywords) or "—")
    table.add_row("Apply URL", detail.apply_url)
    return Group(header, Text(), table)
