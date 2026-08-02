"""Tests for the shared CLI console/theme in :mod:`atlas.cli.console`."""

from __future__ import annotations

from atlas.cli.console import ATLAS_THEME, console, error_console, print_json_line


def test_theme_defines_semantic_styles() -> None:
    # Commands reference these names instead of raw colors; they must all exist so
    # any themed renderable resolves through the shared console.
    for name in ("success", "warning", "error", "heading", "muted", "accent", "ok", "bad"):
        assert name in ATLAS_THEME.styles


def test_consoles_share_the_theme() -> None:
    assert console.get_style("accent") == ATLAS_THEME.styles["accent"]
    assert error_console.get_style("error") == ATLAS_THEME.styles["error"]


def test_error_console_writes_to_stderr() -> None:
    assert error_console.stderr is True
    assert console.stderr is False


def test_print_json_line_emits_verbatim_unstyled() -> None:
    payload = '{"healthy": true, "note": "[not-markup]"}'
    with console.capture() as capture:
        print_json_line(payload)
    # The JSON is emitted exactly, with no Rich markup interpretation or styling.
    assert capture.get().strip() == payload
