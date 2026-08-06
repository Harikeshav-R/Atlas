"""Tests for the desktop-notification boundary in :mod:`atlas.platform.notifier`.

The production :func:`atlas.platform.notifier.default_notifier` posts a real
desktop notification and is ``# pragma: no cover``; the hermetic suite drives the
post flow through the injected :class:`~tests.conftest.FakeNotifier` instead. Here
we cover the protocol contract and the fake's recording/raising behaviour.
"""

from __future__ import annotations

import pytest

from atlas.platform.notifier import Notifier, NotifyError
from tests.conftest import FakeNotifier


def test_fake_notifier_satisfies_the_protocol() -> None:
    notifier = FakeNotifier()
    assert isinstance(notifier, Notifier)


def test_fake_notifier_records_notifications() -> None:
    notifier = FakeNotifier()
    notifier("New match", "Acme — Senior Engineer (92)")
    notifier("Deadline", "OA due in 6h")
    assert notifier.notifications == [
        ("New match", "Acme — Senior Engineer (92)"),
        ("Deadline", "OA due in 6h"),
    ]


def test_fake_notifier_can_raise_notify_error() -> None:
    notifier = FakeNotifier(raises=NotifyError("boom"))
    with pytest.raises(NotifyError, match="boom"):
        notifier("New match", "Acme — Senior Engineer (92)")
    # The notification is still recorded before raising.
    assert notifier.notifications == [("New match", "Acme — Senior Engineer (92)")]
