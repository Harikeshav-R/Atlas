"""Re-render and open an application's prepared materials (PROJECT.md §9, §5.11).

The ``atlas render`` and ``atlas open`` commands work on an existing
:class:`~atlas.db.models.Application` and its latest materials — the tailored
resume and the cover letter — without any AI:

- :func:`rerender_application` re-renders each material's **persisted** structured
  content (the tailored resume's ``final_content`` :class:`~atlas.render.structure.ResumeContext`
  and the cover letter's ``content`` :class:`~atlas.coverletter.structure.CoverLetterDraft`)
  to fresh PDFs, deterministically. Whichever material doesn't exist is skipped.
- :func:`open_application` opens each material's already-rendered PDF in the OS
  default viewer via the injected :class:`~atlas.platform.opener.FileOpener`.

Every external boundary (PDF renderer, file opener, clock, renders dir) is
injected, so both flows run offline in tests with fakes (AGENTS.md §6.2).
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from pydantic import BaseModel

from atlas.coverletter.context import build_cover_letter_context
from atlas.coverletter.repository import get_latest_cover_letter
from atlas.coverletter.structure import CoverLetterDraft
from atlas.db.models import Company, JobPosting
from atlas.profiles.repository import get_user
from atlas.render.store import write_pdf
from atlas.render.structure import ResumeContext
from atlas.render.themes import render_cover_letter_html, render_resume_html
from atlas.resume.service import utcnow
from atlas.tailor.repository import get_application, get_latest_tailored_resume

if TYPE_CHECKING:
    from collections.abc import Callable
    from datetime import datetime
    from pathlib import Path

    from sqlmodel import Session

    from atlas.platform.opener import FileOpener
    from atlas.render.renderer import PdfRenderer

__all__ = [
    "OpenOutcome",
    "RerenderOutcome",
    "open_application",
    "rerender_application",
]

_DEFAULT_NAME = "Candidate"
_DEFAULT_SLUG = "materials"


class RerenderOutcome(BaseModel):
    """The result of :func:`rerender_application`.

    Attributes:
        application_id: The application whose materials were re-rendered.
        resume_path: The re-rendered tailored-resume PDF path, or ``None`` if the
            application has no tailored resume yet.
        cover_letter_path: The re-rendered cover-letter PDF path, or ``None`` if
            the application has no cover letter yet.
    """

    application_id: int
    resume_path: str | None
    cover_letter_path: str | None


class OpenOutcome(BaseModel):
    """The result of :func:`open_application`.

    Attributes:
        application_id: The application whose materials were opened.
        opened: The PDF paths that were opened, in order.
    """

    application_id: int
    opened: list[str]


def rerender_application(
    session: Session,
    application_id: int,
    *,
    renderer: PdfRenderer,
    resume_theme: str,
    cover_theme: str,
    clock: Callable[[], datetime] = utcnow,
    renders_dir: Path | None = None,
) -> RerenderOutcome:
    """Re-render an application's latest materials to fresh PDFs (no AI).

    Renders the latest tailored resume (from its stored ``final_content``) and the
    latest cover letter (from its stored ``content``) to PDFs, skipping whichever
    material the application does not have yet.

    Args:
        session: The open session/transaction to work within.
        application_id: The application to re-render.
        renderer: The injected HTML → PDF renderer.
        resume_theme: The resume theme name (from ``[render] resume_theme``).
        cover_theme: The cover-letter theme name (from ``[render] cover_theme``).
        clock: The clock for the cover letter's date line (injectable for tests).
        renders_dir: Where to write the PDFs (injectable for tests).

    Returns:
        A :class:`RerenderOutcome` with each material's path (or ``None``).

    Raises:
        ApplicationNotFoundError: If no application has ``application_id``.
    """
    application = get_application(session, application_id)
    assert application.id is not None
    name, company = _name_and_company(session, application.job_posting_id)

    resume_path: str | None = None
    tailored = get_latest_tailored_resume(session, application.id)
    if tailored is not None:
        resume_context = ResumeContext.model_validate(tailored.final_content)
        resume_result = renderer(html=render_resume_html(resume_context, theme=resume_theme))
        resume_path = write_pdf(
            resume_result.pdf_bytes,
            filename=f"{_slug(name)}__{_slug(company)}__tailored.pdf",
            renders_dir=renders_dir,
        )

    cover_letter_path: str | None = None
    letter = get_latest_cover_letter(session, application.id)
    if letter is not None:
        draft = CoverLetterDraft.model_validate(letter.content)
        user = get_user(session)
        contact_lines = [user.email] if user is not None and user.email else []
        cover_context = build_cover_letter_context(
            draft,
            name=name,
            contact_lines=contact_lines,
            company=company,
            date=clock().strftime("%B %d, %Y"),
        )
        cover_result = renderer(html=render_cover_letter_html(cover_context, theme=cover_theme))
        cover_letter_path = write_pdf(
            cover_result.pdf_bytes,
            filename=f"{_slug(name)}__{_slug(company)}__cover.pdf",
            renders_dir=renders_dir,
        )

    return RerenderOutcome(
        application_id=application.id,
        resume_path=resume_path,
        cover_letter_path=cover_letter_path,
    )


def open_application(
    session: Session,
    application_id: int,
    *,
    opener: FileOpener,
) -> OpenOutcome:
    """Open an application's rendered material PDFs in the OS default viewer.

    Opens the latest tailored-resume and cover-letter PDFs (whichever exist and
    have a stored path) via the injected opener.

    Args:
        session: The open session/transaction to read within.
        application_id: The application whose materials to open.
        opener: The injected file opener.

    Returns:
        An :class:`OpenOutcome` listing the paths that were opened.

    Raises:
        ApplicationNotFoundError: If no application has ``application_id``.
        FileOpenError: If a referenced PDF cannot be opened.
    """
    from pathlib import Path

    application = get_application(session, application_id)
    assert application.id is not None

    opened: list[str] = []
    tailored = get_latest_tailored_resume(session, application.id)
    if tailored is not None and tailored.rendered_pdf_ref:
        opener(Path(tailored.rendered_pdf_ref))
        opened.append(tailored.rendered_pdf_ref)
    letter = get_latest_cover_letter(session, application.id)
    if letter is not None and letter.rendered_pdf_ref:
        opener(Path(letter.rendered_pdf_ref))
        opened.append(letter.rendered_pdf_ref)

    return OpenOutcome(application_id=application.id, opened=opened)


def _name_and_company(session: Session, job_posting_id: int) -> tuple[str, str]:
    """Resolve the candidate name and company for filename slugs."""
    user = get_user(session)
    name = user.name if user is not None else _DEFAULT_NAME
    posting = session.get(JobPosting, job_posting_id)
    assert posting is not None  # an application always references its posting
    company = session.get(Company, posting.company_id)
    assert company is not None
    return name, company.name


def _slug(text: str) -> str:
    """Return a filesystem-safe slug for ``text`` (fallback when empty)."""
    slug = re.sub(r"[^A-Za-z0-9]+", "_", text).strip("_")
    return slug or _DEFAULT_SLUG
