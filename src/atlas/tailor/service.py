"""Resume-tailoring orchestration for a stored posting (PROJECT.md §5.7).

:func:`tailor_posting` is the domain layer between the CLI and the tailoring
primitives. Over an open :class:`~sqlmodel.Session`, with the AI provider, PDF
renderer, clock, and renders directory injected, it:

1. loads the posting + company (:mod:`atlas.scrape.repository`), the active
   profile (:mod:`atlas.profiles.repository`), and the latest master-resume
   version + blocks (:mod:`atlas.resume.repository`), erroring if any is missing;
2. asks the AI to select and reword relevant blocks
   (:mod:`atlas.tailor.ai_tailor`), translating an
   :class:`~atlas.ai.base.LLMOutputError` into a
   :class:`~atlas.tailor.errors.TailoringOutputError`;
3. runs the deterministic date-restore safety net (:mod:`atlas.tailor.safety`),
   maps the tailored items back onto real source blocks by content id
   (:mod:`atlas.tailor.blocks`), and builds the render view model
   (:func:`atlas.render.build_resume_context`);
4. packs the render to one page (:mod:`atlas.tailor.onepage`) and writes the PDF
   (:func:`atlas.render.write_pdf`);
5. gets-or-creates the :class:`~atlas.db.models.Application` and appends a
   versioned :class:`~atlas.db.models.TailoredResume`, returning a small
   serializable :class:`TailorOutcome` for the CLI.

Every external boundary (provider, renderer, clock, renders dir) is injected, so
the whole flow runs offline in tests with fakes (AGENTS.md §6.2).
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from pydantic import BaseModel

from atlas.ai.base import LLMOutputError
from atlas.db.models import Company
from atlas.profiles.repository import get_active_profile, get_user
from atlas.render.context import build_resume_context
from atlas.render.store import write_pdf
from atlas.resume.repository import get_blocks, get_latest_master_resume
from atlas.resume.service import utcnow
from atlas.scrape.repository import get_posting
from atlas.tailor.ai_tailor import select_and_reword
from atlas.tailor.blocks import render_blocks
from atlas.tailor.errors import NoActiveProfileError, NoMasterResumeError, TailoringOutputError
from atlas.tailor.onepage import pack_to_one_page
from atlas.tailor.repository import create_tailored_resume, get_or_create_application
from atlas.tailor.safety import restore_dates

if TYPE_CHECKING:
    from collections.abc import Callable
    from datetime import datetime
    from pathlib import Path

    from sqlmodel import Session

    from atlas.ai.base import LLMProvider
    from atlas.render.renderer import PdfRenderer

__all__ = ["TailorOutcome", "tailor_posting"]

#: Display name used when onboarding has not run yet (no user row).
_DEFAULT_NAME = "Resume"

#: Filename-stem fallback when a name/company has no slug-able characters.
_DEFAULT_SLUG = "resume"


class TailorOutcome(BaseModel):
    """The result of :func:`tailor_posting`.

    Attributes:
        application_id: The owning application's id.
        tailored_resume_id: The persisted tailored-resume row's id.
        version: The tailored resume's version within the application.
        posting_id: The tailored posting's id.
        title: The posting's title.
        company: The posting's company name.
        path: The on-disk path to the rendered PDF.
        page_count: The number of pages the final render measured.
        one_page: Whether the tailored resume fit a single page.
        included_count: How many resume blocks were included.
        trimmed: How many entries the one-page loop trimmed.
        gaps: Desired posting keywords/skills not truthfully supportable.
    """

    application_id: int
    tailored_resume_id: int
    version: int
    posting_id: int
    title: str
    company: str
    path: str
    page_count: int
    one_page: bool
    included_count: int
    trimmed: int
    gaps: list[str]


def tailor_posting(
    session: Session,
    posting_id: int,
    *,
    provider: LLMProvider,
    renderer: PdfRenderer,
    honesty_level: str,
    theme: str,
    enforce_one_page: bool = True,
    clock: Callable[[], datetime] = utcnow,
    renders_dir: Path | None = None,
) -> TailorOutcome:
    """Tailor the posting ``posting_id`` into a one-page resume PDF and persist it.

    Args:
        session: The open session/transaction to work within.
        posting_id: The id of the posting to tailor toward.
        provider: The AI backend (or failover chain) to call.
        renderer: The injected HTML → PDF renderer for the one-page loop.
        honesty_level: The resolved honesty level governing rewording.
        theme: The resume theme name (from ``[render] resume_theme``).
        enforce_one_page: Whether to run the one-page trim loop.
        clock: The clock for timestamps (injectable for tests).
        renders_dir: Where to write the PDF (injectable for tests).

    Returns:
        A :class:`TailorOutcome` describing the persisted tailored resume.

    Raises:
        JobPostingNotFoundError: If no posting has ``posting_id``.
        NoActiveProfileError: If no profile is active.
        NoMasterResumeError: If no master resume has been set.
        TailoringOutputError: If the AI never produces a usable tailored resume.
    """
    posting = get_posting(session, posting_id)
    assert posting.id is not None  # persisted rows always have an id

    profile = get_active_profile(session)
    if profile is None:
        raise NoActiveProfileError
    assert profile.id is not None

    resume = get_latest_master_resume(session)
    if resume is None:
        raise NoMasterResumeError
    assert resume.id is not None
    source_blocks = get_blocks(session, resume.id)

    company_name = _company_name(session, posting.company_id)
    now = clock()

    try:
        tailored = select_and_reword(
            provider,
            posting=posting,
            company=company_name,
            emphasis=list(profile.tailoring_emphasis),
            honesty_level=honesty_level,
            blocks=source_blocks,
        )
    except LLMOutputError as exc:
        raise TailoringOutputError(
            f"Could not tailor posting {posting_id}: no usable tailored resume."
        ) from exc

    items = restore_dates(tailored.items, source_blocks)
    tailored_blocks = render_blocks(items, source_blocks)

    user = get_user(session)
    name = user.name if user is not None else _DEFAULT_NAME
    context = build_resume_context(tailored_blocks, name=name)

    packed = pack_to_one_page(
        context, renderer=renderer, theme=theme, enforce_one_page=enforce_one_page
    )

    application = get_or_create_application(
        session, job_posting_id=posting.id, profile_id=profile.id, clock=now
    )
    assert application.id is not None

    filename = f"{_slug(name)}__{_slug(company_name)}__tailored.pdf"
    pdf_path = write_pdf(packed.result.pdf_bytes, filename=filename, renders_dir=renders_dir)

    created = create_tailored_resume(
        session,
        application_id=application.id,
        master_resume_version=resume.version,
        selections=[item.model_dump(mode="json") for item in items],
        final_content=packed.context.model_dump(mode="json"),
        rendered_pdf_ref=pdf_path,
        decisions=[
            {"content_id": item.content_id, "included": item.included, "reason": item.reason}
            for item in tailored.items
        ],
        created_at=now,
    )
    assert created.id is not None

    return TailorOutcome(
        application_id=application.id,
        tailored_resume_id=created.id,
        version=created.version,
        posting_id=posting.id,
        title=posting.title,
        company=company_name,
        path=pdf_path,
        page_count=packed.result.page_count,
        one_page=packed.result.page_count <= 1,
        included_count=len(tailored_blocks),
        trimmed=packed.trimmed,
        gaps=list(tailored.gaps),
    )


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
