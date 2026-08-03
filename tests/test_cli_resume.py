"""Tests for the resume reporting/persistence logic in :mod:`atlas.cli.resume`."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from atlas.cli.console import console
from atlas.cli.resume import (
    ResumeStatusReport,
    ResumeVersionSummary,
    build_resume_report,
    ingest_resume,
    read_source,
    render_resume_status,
    reparse_resume,
)
from atlas.db import session_scope
from atlas.resume.errors import MasterResumeNotFoundError, ResumeSourceError

if TYPE_CHECKING:
    from pathlib import Path

    from sqlalchemy.engine import Engine

_MARKDOWN = "# Sam\n\n## Skills\n\n- Python\n- Rust"


def _rendered(report: ResumeStatusReport) -> str:
    with console.capture() as capture:
        console.print(render_resume_status(report))
    return capture.get()


def test_read_source_reads_text(tmp_path: Path) -> None:
    path = tmp_path / "resume.md"
    path.write_text(_MARKDOWN, encoding="utf-8")
    assert read_source(path) == _MARKDOWN


def test_read_source_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(ResumeSourceError):
        read_source(tmp_path / "nope.md")


def test_read_source_directory_raises(tmp_path: Path) -> None:
    with pytest.raises(ResumeSourceError):
        read_source(tmp_path)


def test_ingest_resume_creates_then_noops(db_engine: Engine, tmp_path: Path) -> None:
    path = tmp_path / "resume.md"
    path.write_text(_MARKDOWN, encoding="utf-8")
    with session_scope(db_engine) as session:
        first = ingest_resume(session, path)
    assert first.created is True
    assert first.version == 1
    assert first.block_count == 3
    with session_scope(db_engine) as session:
        second = ingest_resume(session, path)
    assert second.created is False
    assert second.version == 1


def test_reparse_resume_versions(db_engine: Engine, tmp_path: Path) -> None:
    path = tmp_path / "resume.md"
    path.write_text(_MARKDOWN, encoding="utf-8")
    with session_scope(db_engine) as session:
        ingest_resume(session, path)
    with session_scope(db_engine) as session:
        outcome = reparse_resume(session)
    assert outcome.version == 2
    assert outcome.created is True


def test_reparse_without_resume_raises(db_engine: Engine) -> None:
    with session_scope(db_engine) as session, pytest.raises(MasterResumeNotFoundError):
        reparse_resume(session)


def test_build_report_reflects_versions(db_engine: Engine, tmp_path: Path) -> None:
    path = tmp_path / "resume.md"
    path.write_text(_MARKDOWN, encoding="utf-8")
    with session_scope(db_engine) as session:
        ingest_resume(session, path)
    with session_scope(db_engine) as session:
        report = build_resume_report(session)
    assert report.latest_version == 1
    assert len(report.versions) == 1
    summary = report.versions[0]
    assert summary.version == 1
    assert summary.block_count == 3
    assert summary.source_path == str(path)


def test_build_report_empty(db_engine: Engine) -> None:
    with session_scope(db_engine) as session:
        report = build_resume_report(session)
    assert report.latest_version is None
    assert report.versions == []


def test_render_empty_report_hints_at_set() -> None:
    text = _rendered(ResumeStatusReport(versions=[], latest_version=None))
    assert "atlas resume set" in text


def test_render_report_shows_versions_and_latest_mark() -> None:
    report = ResumeStatusReport(
        versions=[
            ResumeVersionSummary(
                version=1, source_path="/home/sam/resume.md", block_count=3, created_at="2026-08-03"
            ),
            ResumeVersionSummary(
                version=2, source_path=None, block_count=4, created_at="2026-08-04"
            ),
        ],
        latest_version=2,
    )
    text = _rendered(report)
    assert "Master resume versions" in text
    assert "latest version" in text
    # A version with no source path renders the em-dash placeholder.
    assert "—" in text


def test_report_json_round_trips() -> None:
    report = ResumeStatusReport(
        versions=[
            ResumeVersionSummary(
                version=1, source_path=None, block_count=2, created_at="2026-08-03"
            )
        ],
        latest_version=1,
    )
    assert ResumeStatusReport.model_validate_json(report.model_dump_json()) == report
