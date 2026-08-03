"""Master-resume reporting and persistence for the Atlas CLI.

The ``atlas resume`` commands (PROJECT.md §9) keep their Typer wiring thin in
:mod:`atlas.cli.main` and delegate here, mirroring the ``atlas profile`` split
(:mod:`atlas.cli.profile`): this module holds the **pure, I/O-light logic** —
reading the source file at a single injectable boundary, orchestrating an ingest
or reparse through the service within one
:func:`~atlas.db.session.session_scope`, and building/rendering a serializable
view of the stored versions. Keeping the logic here means it is testable against
the in-memory ``db_engine`` fixture without invoking the CLI (AGENTS.md §6.2).
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from pydantic import BaseModel
from rich.console import Group
from rich.table import Table
from rich.text import Text

from atlas.resume.errors import ResumeSourceError
from atlas.resume.repository import get_latest_master_resume, list_versions
from atlas.resume.service import apply_reparse, apply_set

if TYPE_CHECKING:
    from rich.console import RenderableType
    from sqlmodel import Session

    from atlas.resume.service import SetOutcome

__all__ = [
    "ResumeStatusReport",
    "ResumeVersionSummary",
    "build_resume_report",
    "ingest_resume",
    "read_source",
    "render_resume_status",
    "reparse_resume",
]


class ResumeVersionSummary(BaseModel):
    """A compact, serializable view of one stored master-resume version.

    Attributes:
        version: The version number.
        source_path: The path the version was read from, if any.
        block_count: How many blocks the version parsed into.
        created_at: When the version was created, as an ISO-8601 string.
    """

    version: int
    source_path: str | None
    block_count: int
    created_at: str


class ResumeStatusReport(BaseModel):
    """The result of ``atlas resume show``.

    Attributes:
        versions: One :class:`ResumeVersionSummary` per stored version, oldest
            first.
        latest_version: The current (highest) version number, or ``None`` when no
            master resume has been set yet.
    """

    versions: list[ResumeVersionSummary]
    latest_version: int | None


def read_source(path: Path) -> str:
    """Read the master-resume Markdown at ``path``.

    The single file-reading boundary for ``atlas resume set``; kept here (not in
    the Typer command) so error handling is covered without the CLI.

    Raises:
        ResumeSourceError: If the path is missing, is a directory, or cannot be
            read as UTF-8 text.
    """
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise ResumeSourceError(f"Could not read resume file at {path}: {exc}") from exc


def ingest_resume(session: Session, path: Path) -> SetOutcome:
    """Read ``path`` and ingest it as a new version if the content changed.

    Raises:
        ResumeSourceError: If the file cannot be read.
    """
    raw_markdown = read_source(path)
    return apply_set(session, raw_markdown=raw_markdown, source_path=str(path))


def reparse_resume(session: Session) -> SetOutcome:
    """Re-parse the latest version's stored source into a new version.

    Raises:
        MasterResumeNotFoundError: If no master resume has been set yet.
    """
    return apply_reparse(session)


def build_resume_report(session: Session) -> ResumeStatusReport:
    """Build a :class:`ResumeStatusReport` from every stored version.

    Pure over the session: reads the versions and maps each into a
    :class:`ResumeVersionSummary`, taking the block count from the stored
    ``parsed`` snapshot.
    """
    summaries = [
        ResumeVersionSummary(
            version=resume.version,
            source_path=resume.source_path,
            block_count=len(resume.parsed.get("blocks", [])),
            created_at=resume.created_at.isoformat(),
        )
        for resume in list_versions(session)
    ]
    latest = get_latest_master_resume(session)
    return ResumeStatusReport(
        versions=summaries,
        latest_version=latest.version if latest is not None else None,
    )


def render_resume_status(report: ResumeStatusReport) -> RenderableType:
    """Render a :class:`ResumeStatusReport` as a styled Rich renderable.

    Produces a table of versions (marking the latest) using the shared semantic
    theme so it matches the rest of the CLI. An empty report renders a muted hint
    pointing at ``atlas resume set``. Machine-readable output is produced
    separately via :meth:`ResumeStatusReport.model_dump_json`.
    """
    if not report.versions:
        return Text("No master resume yet — run `atlas resume set <path>`.", style="muted")
    table = Table(title="Master resume versions", title_style="heading", title_justify="left")
    table.add_column("", no_wrap=True)  # latest glyph
    table.add_column("Version", justify="right", no_wrap=True)
    table.add_column("Blocks", justify="right", no_wrap=True)
    table.add_column("Source")
    table.add_column("Created")
    for version in report.versions:
        is_latest = version.version == report.latest_version
        glyph = Text("●", style="ok") if is_latest else Text("○", style="muted")
        table.add_row(
            glyph,
            str(version.version),
            str(version.block_count),
            Text(version.source_path or "—", style="muted"),
            Text(version.created_at, style="muted"),
        )
    latest_note = Text("● = latest version", style="muted")
    return Group(table, Text(), latest_note)
