"""Jinja2 HTML themes for rendered resumes (PROJECT.md §5.11).

Resume themes are HTML/CSS template directories under ``themes/<name>/``: a
``resume.html.jinja`` rendered against a :class:`~atlas.render.structure.ResumeContext`
plus a sibling ``resume.css``. :func:`render_resume_html` renders the HTML with the
CSS inlined into a ``<style>`` block, so the produced document is self-contained and
the PDF renderer needs no base URL or on-disk file resolution.

The Jinja environment here uses ``autoescape=True`` (this is HTML built from
user-supplied resume text, unlike the plain-text prompt templates in
:mod:`atlas.ai.prompts`, whose environment deliberately leaves escaping off). The
themes directory is an injectable argument defaulting to the bundled ``themes/``
(shipped in the wheel with the package), so tests can point at a ``tmp_path`` theme.
"""

from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, StrictUndefined, select_autoescape

from atlas.render.errors import ThemeNotFoundError
from atlas.render.structure import CoverLetterContext, ResumeContext

__all__ = ["default_themes_dir", "render_cover_letter_html", "render_resume_html"]

#: The bundled themes directory (shipped in the wheel with the package).
_THEMES_DIR = Path(__file__).resolve().parent / "themes"

#: The resume template and stylesheet file names each resume theme must contain.
_TEMPLATE_NAME = "resume.html.jinja"
_STYLESHEET_NAME = "resume.css"

#: The cover-letter template and stylesheet file names each cover theme must contain.
_COVER_TEMPLATE_NAME = "cover.html.jinja"
_COVER_STYLESHEET_NAME = "cover.css"

#: One shared Jinja2 environment for HTML themes. ``autoescape`` is on (HTML from
#: user resume text); ``StrictUndefined`` turns a missing context variable into an
#: error rather than silently emitting an empty string. Templates are rendered from
#: their read text via :meth:`~jinja2.Environment.from_string`, so no loader is set.
_ENV = Environment(
    undefined=StrictUndefined,
    autoescape=select_autoescape(default=True, default_for_string=True),
    trim_blocks=True,
    lstrip_blocks=True,
)


def default_themes_dir() -> Path:
    """Return the bundled themes directory."""
    return _THEMES_DIR


def render_resume_html(
    context: ResumeContext, *, theme: str, themes_dir: Path | None = None
) -> str:
    """Render ``context`` to a self-contained HTML string using ``theme``.

    Reads ``<themes_dir>/<theme>/resume.html.jinja`` and its sibling
    ``resume.css``, renders the template against ``context`` with the CSS inlined,
    and returns the HTML.

    Args:
        context: The resume view model to render.
        theme: The theme directory name.
        themes_dir: The directory holding theme subdirectories; defaults to the
            bundled themes (a ``tmp_path`` is injected in tests).

    Returns:
        The rendered, self-contained HTML document.

    Raises:
        ThemeNotFoundError: If the theme has no ``resume.html.jinja`` template or
            no ``resume.css`` stylesheet.
    """
    return _render_theme(
        theme,
        themes_dir=themes_dir,
        template_name=_TEMPLATE_NAME,
        stylesheet_name=_STYLESHEET_NAME,
        resume=context,
    )


def render_cover_letter_html(
    context: CoverLetterContext, *, theme: str, themes_dir: Path | None = None
) -> str:
    """Render ``context`` to a self-contained cover-letter HTML string using ``theme``.

    Reads ``<themes_dir>/<theme>/cover.html.jinja`` and its sibling ``cover.css``,
    renders the template against ``context`` (as ``letter``) with the CSS inlined,
    and returns the HTML. Mirrors :func:`render_resume_html` for cover letters.

    Args:
        context: The cover-letter view model to render.
        theme: The theme directory name (from ``[render] cover_theme``).
        themes_dir: The directory holding theme subdirectories; defaults to the
            bundled themes (a ``tmp_path`` is injected in tests).

    Returns:
        The rendered, self-contained HTML document.

    Raises:
        ThemeNotFoundError: If the theme has no ``cover.html.jinja`` template or
            no ``cover.css`` stylesheet.
    """
    return _render_theme(
        theme,
        themes_dir=themes_dir,
        template_name=_COVER_TEMPLATE_NAME,
        stylesheet_name=_COVER_STYLESHEET_NAME,
        letter=context,
    )


def _render_theme(
    theme: str,
    *,
    themes_dir: Path | None,
    template_name: str,
    stylesheet_name: str,
    **context: object,
) -> str:
    """Read a theme's template + stylesheet and render the HTML with the CSS inlined.

    Raises :class:`~atlas.render.errors.ThemeNotFoundError` if either file is
    missing. ``context`` is passed to the template alongside the inlined ``css``.
    """
    theme_dir = (themes_dir if themes_dir is not None else _THEMES_DIR) / theme
    try:
        template_text = (theme_dir / template_name).read_text(encoding="utf-8")
        css = (theme_dir / stylesheet_name).read_text(encoding="utf-8")
    except OSError as exc:
        raise ThemeNotFoundError(theme) from exc
    return _ENV.from_string(template_text).render(css=css, **context)
