"""Render a resume to a one-page PDF via HTML/CSS (PROJECT.md §5.11).

Atlas renders resumes through an HTML/CSS → PDF pipeline: a versioned Jinja2 HTML
theme (:mod:`atlas.render.themes`) rendered against a view model
(:mod:`atlas.render.context`, :mod:`atlas.render.structure`), turned into a PDF by
an injectable :class:`~atlas.render.renderer.PdfRenderer` (WeasyPrint by default,
behind a lazy-import seam) that also reports the measured page count — the signal
the one-page enforcement loop (§5.7) consumes. Rendered PDFs are stored on disk
(:mod:`atlas.render.store`), referenced by path, never as DB blobs (§6).

This package owns the view-model structures, the block-to-view mapping, the theme
loader, the renderer boundary, the on-disk store, the render orchestration
(:mod:`atlas.render.service`), and the package error hierarchy
(:mod:`atlas.render.errors`).
"""

from __future__ import annotations

from atlas.render.context import build_resume_context
from atlas.render.errors import NoMasterResumeError, RenderError, ThemeNotFoundError
from atlas.render.renderer import PdfRenderer, build_renderer, default_weasyprint_renderer
from atlas.render.service import RenderOutcome, render_master_resume
from atlas.render.store import default_renders_dir, write_pdf
from atlas.render.structure import (
    CoverLetterContext,
    RenderResult,
    ResumeContext,
    ResumeEntry,
    ResumeSection,
)
from atlas.render.themes import (
    default_themes_dir,
    render_cover_letter_html,
    render_resume_html,
)

__all__ = [
    "CoverLetterContext",
    "NoMasterResumeError",
    "PdfRenderer",
    "RenderError",
    "RenderOutcome",
    "RenderResult",
    "ResumeContext",
    "ResumeEntry",
    "ResumeSection",
    "ThemeNotFoundError",
    "build_renderer",
    "build_resume_context",
    "default_renders_dir",
    "default_themes_dir",
    "default_weasyprint_renderer",
    "render_cover_letter_html",
    "render_master_resume",
    "render_resume_html",
    "write_pdf",
]
