"""Typed structures for the rendering pipeline (PROJECT.md §5.11).

A :class:`ResumeContext` is the theme's view model — the shape a resume HTML
theme is rendered against — and a :class:`RenderResult` is what a
:class:`~atlas.render.renderer.PdfRenderer` returns (the PDF bytes plus the
measured page count the one-page enforcement loop consumes, §5.7 step 2). Both
are plain Pydantic models with no I/O, like :mod:`atlas.matching.structure`.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

__all__ = ["RenderResult", "ResumeContext", "ResumeEntry", "ResumeSection"]


class _Base(BaseModel):
    """Base model that ignores unknown keys (forward-compatible view models)."""

    model_config = ConfigDict(extra="ignore")


class RenderResult(BaseModel):
    """The outcome of rendering HTML to PDF.

    Attributes:
        pdf_bytes: The rendered PDF document bytes.
        page_count: The number of pages the renderer measured — the signal the
            one-page enforcement loop (PROJECT.md §5.7 step 2) adjusts against.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    pdf_bytes: bytes
    page_count: int


class ResumeEntry(_Base):
    """One item within a resume section (e.g. one job, one project).

    Attributes:
        lines: The entry's text lines in document order; the first is typically a
            title/header and the rest are bullet or detail lines.
    """

    lines: list[str] = Field(default_factory=list)


class ResumeSection(_Base):
    """A titled group of resume entries (e.g. Experience, Skills).

    Attributes:
        heading: The section's display heading.
        entries: The section's entries in document order.
    """

    heading: str = ""
    entries: list[ResumeEntry] = Field(default_factory=list)


class ResumeContext(_Base):
    """The full view model a resume theme is rendered against.

    Attributes:
        name: The candidate's display name (the resume header).
        contact_lines: Contact/header lines shown under the name.
        sections: The resume's body sections in document order.
    """

    name: str = ""
    contact_lines: list[str] = Field(default_factory=list)
    sections: list[ResumeSection] = Field(default_factory=list)
