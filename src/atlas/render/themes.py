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
from atlas.render.structure import ResumeContext

__all__ = ["default_themes_dir", "render_resume_html"]

#: The bundled themes directory (shipped in the wheel with the package).
_THEMES_DIR = Path(__file__).resolve().parent / "themes"

#: The template and stylesheet file names each theme directory must contain.
_TEMPLATE_NAME = "resume.html.jinja"
_STYLESHEET_NAME = "resume.css"

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
    theme_dir = (themes_dir if themes_dir is not None else _THEMES_DIR) / theme
    try:
        template_text = (theme_dir / _TEMPLATE_NAME).read_text(encoding="utf-8")
        css = (theme_dir / _STYLESHEET_NAME).read_text(encoding="utf-8")
    except OSError as exc:
        raise ThemeNotFoundError(theme) from exc
    return _ENV.from_string(template_text).render(resume=context, css=css)
