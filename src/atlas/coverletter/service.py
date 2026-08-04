"""Cover-letter generation orchestration for a posting (PROJECT.md §5.8).

:func:`write_application_cover_letter` is the domain layer between the CLI and the
cover-letter primitives. Over an open :class:`~sqlmodel.Session`, with the AI
provider, PDF renderer, clock, and renders directory injected, it:

1. loads the posting + company, the active profile, and the user
   (erroring on a missing posting/profile);
2. gets-or-creates the :class:`~atlas.db.models.Application` and grounds the
   letter in the latest tailored resume's selections if present, else a compact
   master-resume summary (erroring if neither exists);
3. asks the AI to draft the letter (:mod:`atlas.coverletter.ai_write`),
   translating an :class:`~atlas.ai.base.LLMOutputError` into a
   :class:`~atlas.coverletter.errors.CoverLetterOutputError`;
4. builds the render view model (:mod:`atlas.coverletter.context`), renders it to
   HTML through the configured cover theme (:mod:`atlas.render.themes`) and to PDF
   via the injected renderer (once — a cover letter is one page), writes the PDF
   (:func:`atlas.render.write_pdf`), and appends a versioned
   :class:`~atlas.db.models.CoverLetter`, returning a :class:`CoverLetterOutcome`.

Every external boundary (provider, renderer, clock, renders dir) is injected, so
the whole flow runs offline in tests with fakes (AGENTS.md §6.2).
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from pydantic import BaseModel

from atlas.ai.base import LLMOutputError
from atlas.coverletter.ai_write import write_cover_letter
from atlas.coverletter.context import build_cover_letter_context
from atlas.coverletter.errors import (
    CoverLetterOutputError,
    NoActiveProfileError,
    NoMasterResumeError,
)
from atlas.coverletter.repository import create_cover_letter
from atlas.db.models import Company
from atlas.profiles.repository import get_active_profile, get_user
from atlas.render.store import write_pdf
from atlas.render.themes import render_cover_letter_html
from atlas.resume.repository import get_blocks, get_latest_master_resume
from atlas.resume.service import utcnow
from atlas.scrape.repository import get_posting
from atlas.tailor.blocks import tag_blocks_for_prompt
from atlas.tailor.repository import get_latest_tailored_resume, get_or_create_application

if TYPE_CHECKING:
    from collections.abc import Callable
    from datetime import datetime
    from pathlib import Path

    from sqlmodel import Session

    from atlas.ai.base import LLMProvider
    from atlas.render.renderer import PdfRenderer

__all__ = ["CoverLetterOutcome", "write_application_cover_letter"]

#: Display name used when onboarding has not run yet (no user row).
_DEFAULT_NAME = "Candidate"

#: Filename-stem fallback when a name/company has no slug-able characters.
_DEFAULT_SLUG = "cover"

#: Default tone when the caller does not specify one.
_DEFAULT_TONE = "professional"


class CoverLetterOutcome(BaseModel):
    """The result of :func:`write_application_cover_letter`.

    Attributes:
        application_id: The owning application's id.
        cover_letter_id: The persisted cover-letter row's id.
        version: The cover letter's version within the application.
        posting_id: The posting the letter is for.
        title: The posting's title.
        company: The posting's company name.
        path: The on-disk path to the rendered PDF.
        page_count: The number of pages the render measured.
        one_page: Whether the letter fit a single page.
        tone: The tone the letter was written in.
        grounded_on: ``"tailored_resume"`` or ``"master_resume"`` — what the letter
            was grounded in.
        gaps: Desired posting keywords/skills the letter could not truthfully claim.
    """

    application_id: int
    cover_letter_id: int
    version: int
    posting_id: int
    title: str
    company: str
    path: str
    page_count: int
    one_page: bool
    tone: str
    grounded_on: str
    gaps: list[str]


def write_application_cover_letter(
    session: Session,
    posting_id: int,
    *,
    provider: LLMProvider,
    renderer: PdfRenderer,
    honesty_level: str,
    theme: str,
    tone: str = _DEFAULT_TONE,
    clock: Callable[[], datetime] = utcnow,
    renders_dir: Path | None = None,
) -> CoverLetterOutcome:
    """Generate and render a cover letter for ``posting_id`` and persist it.

    Args:
        session: The open session/transaction to work within.
        posting_id: The id of the posting to write a letter for.
        provider: The AI backend (or failover chain) to call.
        renderer: The injected HTML → PDF renderer.
        honesty_level: The resolved honesty level governing the letter's claims.
        theme: The cover-letter theme name (from ``[render] cover_theme``).
        tone: The desired tone.
        clock: The clock for timestamps (injectable for tests).
        renders_dir: Where to write the PDF (injectable for tests).

    Returns:
        A :class:`CoverLetterOutcome` describing the persisted cover letter.

    Raises:
        JobPostingNotFoundError: If no posting has ``posting_id``.
        NoActiveProfileError: If no profile is active.
        NoMasterResumeError: If there is no tailored resume and no master resume
            to ground the letter in.
        CoverLetterOutputError: If the AI never produces a usable letter.
    """
    posting = get_posting(session, posting_id)
    assert posting.id is not None  # persisted rows always have an id

    profile = get_active_profile(session)
    if profile is None:
        raise NoActiveProfileError
    assert profile.id is not None

    company_name = _company_name(session, posting.company_id)
    now = clock()

    application = get_or_create_application(
        session, job_posting_id=posting.id, profile_id=profile.id, clock=now
    )
    assert application.id is not None

    material, grounded_on = _grounding_material(session, application.id)

    try:
        draft = write_cover_letter(
            provider,
            posting=posting,
            company=company_name,
            material=material,
            tone=tone,
            honesty_level=honesty_level,
        )
    except LLMOutputError as exc:
        raise CoverLetterOutputError(
            f"Could not write a cover letter for posting {posting_id}: no usable letter."
        ) from exc

    user = get_user(session)
    name = user.name if user is not None else _DEFAULT_NAME
    contact_lines = [user.email] if user is not None and user.email else []

    context = build_cover_letter_context(
        draft,
        name=name,
        contact_lines=contact_lines,
        company=company_name,
        date=now.strftime("%B %d, %Y"),
    )
    html = render_cover_letter_html(context, theme=theme)
    result = renderer(html=html)

    filename = f"{_slug(name)}__{_slug(company_name)}__cover.pdf"
    pdf_path = write_pdf(result.pdf_bytes, filename=filename, renders_dir=renders_dir)

    created = create_cover_letter(
        session,
        application_id=application.id,
        content=draft.model_dump(mode="json"),
        tone=tone,
        rendered_pdf_ref=pdf_path,
        created_at=now,
    )
    assert created.id is not None

    return CoverLetterOutcome(
        application_id=application.id,
        cover_letter_id=created.id,
        version=created.version,
        posting_id=posting.id,
        title=posting.title,
        company=company_name,
        path=pdf_path,
        page_count=result.page_count,
        one_page=result.page_count <= 1,
        tone=tone,
        grounded_on=grounded_on,
        gaps=list(draft.gaps),
    )


def _grounding_material(session: Session, application_id: int) -> tuple[str, str]:
    """Return the letter's grounding text and its source label.

    Prefers the latest tailored resume's selections; falls back to a compact
    master-resume block summary. Raises :class:`NoMasterResumeError` when neither
    exists (nothing truthful to ground the letter in).
    """
    tailored = get_latest_tailored_resume(session, application_id)
    if tailored is not None and tailored.selections:
        lines = [
            f"- {item.get('final_text', '')}"
            for item in tailored.selections
            if item.get("included", True) and item.get("final_text", "").strip()
        ]
        if lines:
            return "\n".join(lines), "tailored_resume"

    resume = get_latest_master_resume(session)
    if resume is None:
        raise NoMasterResumeError
    assert resume.id is not None
    return tag_blocks_for_prompt(get_blocks(session, resume.id)), "master_resume"


def _company_name(session: Session, company_id: int) -> str:
    """Return the name of the company with ``company_id``.

    A posting always references an existing company (a non-null foreign key), so
    the lookup never misses.
    """
    company = session.get(Company, company_id)
    assert company is not None
    return company.name


def _slug(text: str) -> str:
    """Return a filesystem-safe slug for ``text`` (fallback when empty)."""
    slug = re.sub(r"[^A-Za-z0-9]+", "_", text).strip("_")
    return slug or _DEFAULT_SLUG
