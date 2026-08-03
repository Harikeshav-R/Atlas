"""The HTML → PDF renderer boundary (PROJECT.md §5.11).

Rendering PDFs is an injectable boundary — like the coding-CLI
:class:`~atlas.ai.cli.runner.SubprocessRunner` and the scraper's
:class:`~atlas.scrape.fetcher.Fetcher` — so the default suite stays hermetic and
never imports the heavy WeasyPrint stack (which pulls in Pango/Cairo system libs).
Callers depend on the :class:`PdfRenderer` protocol; production wiring uses
:func:`default_weasyprint_renderer` (which imports ``weasyprint`` lazily, inside
the call), and tests inject a fake that returns a scripted
:class:`~atlas.render.structure.RenderResult`.

:func:`build_renderer` maps the ``[render] engine`` config to an implementation.
Only ``weasyprint`` is implemented today; the ``chromium`` (headless-Playwright
print-to-PDF) backend named in §5.11 is rejected with a clear error until it lands,
so it drops in later without reworking callers.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

from atlas.render.errors import RenderError
from atlas.render.structure import RenderResult

if TYPE_CHECKING:
    from atlas.config.schema import RenderConfig

__all__ = ["PdfRenderer", "build_renderer", "default_weasyprint_renderer"]

#: The config ``engine`` value for the pure-Python default renderer.
_WEASYPRINT_ENGINE = "weasyprint"


@runtime_checkable
class PdfRenderer(Protocol):
    """Callable that renders a self-contained HTML string to a PDF.

    Implementations return a :class:`~atlas.render.structure.RenderResult`
    carrying the PDF bytes and the measured page count (the signal the one-page
    enforcement loop consumes, PROJECT.md §5.7 step 2).
    """

    def __call__(self, *, html: str) -> RenderResult:
        """Render ``html`` to PDF and return its :class:`RenderResult`."""


def default_weasyprint_renderer(*, html: str) -> RenderResult:  # pragma: no cover
    """Render ``html`` to PDF with WeasyPrint, reporting the page count.

    This boundary carries ``# pragma: no cover`` because the default test suite
    never imports WeasyPrint (it needs Pango/Cairo system libs and is slow to
    import, AGENTS.md §6.2); the render flow is exercised through an injected fake
    renderer instead. ``weasyprint`` is imported lazily here so the import cost is
    paid only when a real render happens.
    """
    from weasyprint import HTML

    document = HTML(string=html).render()
    pdf_bytes = document.write_pdf()
    return RenderResult(pdf_bytes=pdf_bytes, page_count=len(document.pages))


def build_renderer(config: RenderConfig) -> PdfRenderer:
    """Return the :class:`PdfRenderer` for the configured ``[render] engine``.

    Args:
        config: The resolved ``[render]`` configuration.

    Returns:
        The renderer implementation for ``config.engine``.

    Raises:
        RenderError: If ``config.engine`` names a backend that is not implemented
            yet (e.g. ``"chromium"``).
    """
    if config.engine == _WEASYPRINT_ENGINE:
        return default_weasyprint_renderer
    raise RenderError(f'Render engine {config.engine!r} is not supported yet; use "weasyprint".')
