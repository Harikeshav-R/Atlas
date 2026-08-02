"""Tests for the ``python -m atlas`` entry point in :mod:`atlas.__main__`."""

from __future__ import annotations

import pytest

import atlas.__main__ as entry


def test_main_invokes_the_app(monkeypatch: pytest.MonkeyPatch) -> None:
    # ``main()`` must delegate to the Typer app exactly once, with no arguments.
    calls: list[tuple[object, ...]] = []
    monkeypatch.setattr(entry, "app", lambda *args: calls.append(args))
    entry.main()
    assert calls == [()]
