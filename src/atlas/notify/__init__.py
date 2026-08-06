"""Desktop notifications fired by the daemon (PROJECT.md §5.16).

The daemon posts native OS notifications for new high-fit matches and upcoming
deadlines even when the TUI is closed. This package holds the pieces behind that:
the best-effort fire-and-forget helper (:mod:`atlas.notify.emit`), the pure
quiet-hours / daily-cap gate (:mod:`atlas.notify.window`), the on-disk
notify-state (:mod:`atlas.notify.state`), and the after-poll orchestrator
(:mod:`atlas.notify.service`). The OS boundary itself is the
:class:`~atlas.platform.notifier.Notifier` seam.
"""

from __future__ import annotations
