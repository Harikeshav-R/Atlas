"""Rendering orchestration for the master resume (PROJECT.md §5.11).

:func:`render_master_resume` is the domain layer between the CLI and the render
primitives. Over an open :class:`~sqlmodel.Session`, with the PDF renderer and the
renders directory injected, it:

1. loads the latest master-resume version and its blocks
   (:mod:`atlas.resume.repository`), erroring if no resume is set;
2. resolves the user's display name (:mod:`atlas.profiles.repository`), falling
   back to a default when onboarding has not run;
3. builds the theme view model (:mod:`atlas.render.context`), renders it to HTML
   through the configured theme (:mod:`atlas.render.themes`), and renders that to
   PDF via the injected :class:`~atlas.render.renderer.PdfRenderer`;
4. writes the PDF under the renders dir (:mod:`atlas.render.store`) and returns a
   small serializable :class:`RenderOutcome` for the CLI (including the measured
   page count and whether it fit one page).

Every external boundary (renderer, renders dir) is injected, so the whole flow
runs offline in tests with a fake renderer and a ``tmp_path`` (AGENTS.md §6.2).
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from pydantic import BaseModel

from atlas.profiles.repository import get_user
from atlas.render.context import build_resume_context
from atlas.render.errors import NoMasterResumeError
from atlas.render.store import write_pdf
from atlas.render.themes import render_resume_html
from atlas.resume.repository import get_blocks, get_latest_master_resume

if TYPE_CHECKING:
    from pathlib import Path

    from sqlmodel import Session

    from atlas.render.renderer import PdfRenderer

__all__ = ["RenderOutcome", "render_master_resume"]

#: Display name used when onboarding has not run yet (no user row).
_DEFAULT_NAME = "Resume"

#: Filename stem fallback when the name has no slug-able characters.
_DEFAULT_SLUG = "resume"


class RenderOutcome(BaseModel):
    """The result of :func:`render_master_resume`.

    Attributes:
        path: The on-disk path to the written PDF.
        page_count: The number of pages the renderer measured.
        one_page: Whether the render fit on a single page.
        version: The master-resume version that was rendered.
        theme: The theme the resume was rendered with.
    """

    path: str
    page_count: int
    one_page: bool
    version: int
    theme: str


def render_master_resume(
    session: Session,
    *,
    renderer: PdfRenderer,
    theme: str,
    renders_dir: Path | None = None,
) -> RenderOutcome:
    """Render the latest master-resume version to a PDF and persist it on disk.

    Args:
        session: The open session/transaction to read within.
        renderer: The injected HTML → PDF renderer.
        theme: The resume theme name (from ``[render] resume_theme``).
        renders_dir: Where to write the PDF (injectable for tests); defaults to
            the data-dir renders directory.

    Returns:
        A :class:`RenderOutcome` describing the written PDF.

    Raises:
        NoMasterResumeError: If no master resume has been set.
        ThemeNotFoundError: If ``theme`` has no template on disk.
    """
    resume = get_latest_master_resume(session)
    if resume is None:
        raise NoMasterResumeError
    assert resume.id is not None  # persisted rows always have an id

    user = get_user(session)
    name = user.name if user is not None else _DEFAULT_NAME

    context = build_resume_context(get_blocks(session, resume.id), name=name)
    html = render_resume_html(context, theme=theme)
    result = renderer(html=html)

    filename = f"{_slug(name)}__resume__v{resume.version}.pdf"
    path = write_pdf(result.pdf_bytes, filename=filename, renders_dir=renders_dir)

    return RenderOutcome(
        path=path,
        page_count=result.page_count,
        one_page=result.page_count <= 1,
        version=resume.version,
        theme=theme,
    )


def _slug(name: str) -> str:
    """Return a filesystem-safe slug for ``name`` (fallback when empty)."""
    slug = re.sub(r"[^A-Za-z0-9]+", "_", name).strip("_")
    return slug or _DEFAULT_SLUG
