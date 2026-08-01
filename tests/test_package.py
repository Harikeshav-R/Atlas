"""Tests for the top-level :mod:`atlas` package.

These smoke tests keep the Phase 0 scaffold honest: the package imports cleanly
and exposes a well-formed version string. They also guarantee the test suite has
something to measure so the 100% coverage gate is meaningful from day one.
"""

from __future__ import annotations

import re
from importlib import metadata

import atlas

# A minimal ``MAJOR.MINOR.PATCH`` version pattern (PEP 440-compatible subset).
_SEMVER = re.compile(r"^\d+\.\d+\.\d+$")


def test_version_is_semver() -> None:
    """The package exposes a ``MAJOR.MINOR.PATCH`` version string."""
    assert _SEMVER.match(atlas.__version__)


def test_version_is_public() -> None:
    """``__version__`` is part of the package's public API surface."""
    assert "__version__" in atlas.__all__


def test_version_matches_installed_metadata() -> None:
    """The in-code version matches the installed distribution metadata.

    Hatchling derives the distribution version from ``atlas.__version__``
    (``[tool.hatch.version]``), so the two must agree once installed.
    """
    assert metadata.version("atlas") == atlas.__version__
