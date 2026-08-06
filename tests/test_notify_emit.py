"""Tests for the best-effort notification dispatch in :mod:`atlas.notify.emit`."""

from __future__ import annotations

import logging

import pytest

from atlas.notify.emit import notify_best_effort
from atlas.platform.notifier import NotifyError
from tests.conftest import FakeNotifier


def test_none_notifier_is_a_noop() -> None:
    # A None notifier is the disabled/unavailable case; must simply do nothing.
    notify_best_effort(None, "New match", "Acme — Senior Engineer (92)")


def test_forwards_to_the_notifier() -> None:
    notifier = FakeNotifier()
    notify_best_effort(notifier, "New match", "Acme — Senior Engineer (92)")
    assert notifier.notifications == [("New match", "Acme — Senior Engineer (92)")]


def test_swallows_a_raising_notifier(caplog: pytest.LogCaptureFixture) -> None:
    # A notification backend that raises must never propagate out of the poll.
    notifier = FakeNotifier(raises=NotifyError("no D-Bus"))
    with caplog.at_level(logging.DEBUG, logger="atlas.notify.emit"):
        notify_best_effort(notifier, "New match", "Acme — Senior Engineer (92)")
    # It was attempted (recorded before raising) and the failure was logged.
    assert notifier.notifications == [("New match", "Acme — Senior Engineer (92)")]
    assert "Notifier raised" in caplog.text
