"""Tests for the renderer boundary in :mod:`atlas.render.renderer`."""

from __future__ import annotations

import pytest

from atlas.config.schema import RenderConfig
from atlas.render.errors import RenderError
from atlas.render.renderer import build_renderer, default_weasyprint_renderer


def test_build_renderer_returns_weasyprint_impl_for_default_engine() -> None:
    renderer = build_renderer(RenderConfig(engine="weasyprint"))
    assert renderer is default_weasyprint_renderer


def test_build_renderer_rejects_unsupported_engine() -> None:
    with pytest.raises(RenderError, match="chromium"):
        build_renderer(RenderConfig(engine="chromium"))
