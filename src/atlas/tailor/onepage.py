"""The one-page render-measure-trim loop (PROJECT.md §5.7 step 2).

Tailoring must fit one page. This driver renders a :class:`~atlas.render.structure.ResumeContext`
to PDF through the injected :class:`~atlas.render.renderer.PdfRenderer`, reads the
measured page count, and — while it overflows — **trims** the lowest-priority
trailing content (the last entry of the last section, dropping empty sections) and
re-renders, up to a bounded iteration cap. It reuses the render pipeline verbatim
(:func:`atlas.render.render_resume_html`), so the tailored resume renders through
the same theme as the master resume. Pure orchestration over the injected renderer;
no I/O of its own.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from atlas.render.themes import render_resume_html

if TYPE_CHECKING:
    from atlas.render.renderer import PdfRenderer
    from atlas.render.structure import RenderResult, ResumeContext

__all__ = ["PackResult", "pack_to_one_page"]

#: Default cap on trim iterations, so a stubbornly-overflowing resume still returns.
_MAX_ITERS = 12


class PackResult:
    """The outcome of :func:`pack_to_one_page`.

    Attributes:
        result: The final :class:`~atlas.render.structure.RenderResult` (PDF bytes
            + measured page count).
        context: The (possibly trimmed) :class:`~atlas.render.structure.ResumeContext`
            that produced it.
        trimmed: How many entries were trimmed to reach the final render.
    """

    def __init__(self, *, result: RenderResult, context: ResumeContext, trimmed: int) -> None:
        """Store the final render, its context, and the trim count."""
        self.result = result
        self.context = context
        self.trimmed = trimmed


def pack_to_one_page(
    context: ResumeContext,
    *,
    renderer: PdfRenderer,
    theme: str,
    enforce_one_page: bool = True,
    max_iters: int = _MAX_ITERS,
) -> PackResult:
    """Render ``context`` to one page, trimming trailing content until it fits.

    Renders once; if ``enforce_one_page`` and the result overflows one page, drops
    the lowest-priority trailing entry and re-renders, repeating until it fits, the
    iteration cap is hit, or nothing remains to trim.

    Args:
        context: The resume view model to render (mutated copies are used, not the
            input).
        renderer: The injected HTML → PDF renderer.
        theme: The resume theme name.
        enforce_one_page: When ``False``, renders once and returns without trimming.
        max_iters: Maximum trim iterations before giving up (best-effort return).

    Returns:
        A :class:`PackResult` with the final render, its context, and the trim count.
    """
    current = context
    result = renderer(html=render_resume_html(current, theme=theme))
    if not enforce_one_page:
        return PackResult(result=result, context=current, trimmed=0)

    trimmed = 0
    while result.page_count > 1 and trimmed < max_iters:
        smaller = _drop_last_entry(current)
        if smaller is None:
            break  # nothing left to trim
        current = smaller
        trimmed += 1
        result = renderer(html=render_resume_html(current, theme=theme))
    return PackResult(result=result, context=current, trimmed=trimmed)


def _drop_last_entry(context: ResumeContext) -> ResumeContext | None:
    """Return a copy of ``context`` with its last section's last entry removed.

    Drops the trailing entry of the last non-empty section; if that empties the
    section, the section is removed too. Returns ``None`` when no entry remains to
    trim (so the caller stops).
    """
    sections = [section.model_copy(deep=True) for section in context.sections]
    for index in range(len(sections) - 1, -1, -1):
        if sections[index].entries:
            sections[index].entries.pop()
            if not sections[index].entries:
                sections.pop(index)
            return context.model_copy(update={"sections": sections})
    return None
