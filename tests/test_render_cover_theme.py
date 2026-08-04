"""Tests for cover-letter HTML rendering in :mod:`atlas.render.themes`."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from atlas.render.errors import ThemeNotFoundError
from atlas.render.structure import CoverLetterContext
from atlas.render.themes import render_cover_letter_html

if TYPE_CHECKING:
    from pathlib import Path


def _context() -> CoverLetterContext:
    return CoverLetterContext(
        name="Sam Lee",
        contact_lines=["sam@example.com"],
        date="August 4, 2026",
        company="Globex",
        greeting="Dear Hiring Manager,",
        paragraphs=["I am excited to apply.", "I led a platform team."],
        closing="Sincerely,",
        signoff_name="Sam Lee",
    )


def test_render_cover_letter_html_includes_content_and_inlined_css() -> None:
    html = render_cover_letter_html(_context(), theme="matching")
    assert "Sam Lee" in html
    assert "Dear Hiring Manager," in html
    assert "I led a platform team." in html
    assert "<style>" in html
    assert "@page" in html


def test_render_cover_letter_html_escapes_special_chars() -> None:
    context = CoverLetterContext(name="Sam <b>Lee</b> & Co", paragraphs=["1 < 2 & 3 > 0"])
    html = render_cover_letter_html(context, theme="matching")
    assert "Sam <b>Lee</b>" not in html
    assert "&lt;b&gt;Lee&lt;/b&gt;" in html
    assert "1 &lt; 2 &amp; 3 &gt; 0" in html


def test_unknown_cover_theme_raises() -> None:
    with pytest.raises(ThemeNotFoundError, match="no-such-theme"):
        render_cover_letter_html(_context(), theme="no-such-theme")


def test_cover_theme_missing_stylesheet_raises(tmp_path: Path) -> None:
    theme_dir = tmp_path / "broken"
    theme_dir.mkdir()
    (theme_dir / "cover.html.jinja").write_text("<html>{{ letter.name }}</html>", encoding="utf-8")
    with pytest.raises(ThemeNotFoundError, match="broken"):
        render_cover_letter_html(_context(), theme="broken", themes_dir=tmp_path)
