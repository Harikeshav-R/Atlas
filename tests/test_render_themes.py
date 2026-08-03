"""Tests for the HTML theme loader in :mod:`atlas.render.themes`."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from atlas.render.errors import ThemeNotFoundError
from atlas.render.structure import ResumeContext, ResumeEntry, ResumeSection
from atlas.render.themes import default_themes_dir, render_resume_html

if TYPE_CHECKING:
    from pathlib import Path


def _context() -> ResumeContext:
    return ResumeContext(
        name="Sam Lee",
        contact_lines=["sam@example.com"],
        sections=[
            ResumeSection(
                heading="Experience",
                entries=[ResumeEntry(lines=["Staff Engineer, Acme", "Led the platform team"])],
            )
        ],
    )


def test_render_resume_html_includes_content_and_inlined_css() -> None:
    html = render_resume_html(_context(), theme="jakes-resume")
    assert "Sam Lee" in html
    assert "sam@example.com" in html
    assert "Led the platform team" in html
    # The stylesheet is inlined into a <style> block (self-contained document).
    assert "<style>" in html
    assert "@page" in html


def test_render_resume_html_escapes_html_special_chars() -> None:
    context = ResumeContext(name="Sam <b>Lee</b> & Co", sections=[])
    html = render_resume_html(context, theme="jakes-resume")
    # autoescape is on: resume text is escaped, not injected as markup.
    assert "Sam <b>Lee</b>" not in html
    assert "&lt;b&gt;Lee&lt;/b&gt;" in html
    assert "&amp; Co" in html


def test_unknown_theme_raises() -> None:
    with pytest.raises(ThemeNotFoundError, match="no-such-theme"):
        render_resume_html(_context(), theme="no-such-theme")


def test_theme_missing_stylesheet_raises(tmp_path: Path) -> None:
    # A theme dir with a template but no resume.css is treated as not found.
    theme_dir = tmp_path / "broken"
    theme_dir.mkdir()
    (theme_dir / "resume.html.jinja").write_text("<html>{{ resume.name }}</html>", encoding="utf-8")
    with pytest.raises(ThemeNotFoundError, match="broken"):
        render_resume_html(_context(), theme="broken", themes_dir=tmp_path)


def test_default_themes_dir_contains_jakes_resume() -> None:
    assert (default_themes_dir() / "jakes-resume" / "resume.css").is_file()
