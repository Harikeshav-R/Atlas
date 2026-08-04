"""Re-render and open an application's prepared materials (PROJECT.md §9, §5.11).

Backs the ``atlas render`` and ``atlas open`` commands: re-rendering the tailored
resume and cover letter from their persisted structured content (no AI), and
opening the rendered PDFs in the OS default viewer. See
:mod:`atlas.materials.service`.
"""

from __future__ import annotations

from atlas.materials.service import (
    OpenOutcome,
    RerenderOutcome,
    open_application,
    rerender_application,
)

__all__ = [
    "OpenOutcome",
    "RerenderOutcome",
    "open_application",
    "rerender_application",
]
