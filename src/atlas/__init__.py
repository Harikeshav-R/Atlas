"""Atlas — a local-first, terminal-native job-application co-pilot.

Atlas discovers matching jobs, tailors a one-page resume and cover letter per
posting from a single master resume, drafts application-form answers, and tracks
every application through to offer.

This package is currently a **Phase 0 scaffold**: it establishes the project
metadata, tooling, and quality gates that later phases build on. Feature modules
(AI providers, discovery, tailoring, rendering, tracking, TUI, …) are introduced
in subsequent phases. See ``docs/PROJECT.md`` for the full design and roadmap.
"""

from __future__ import annotations

__all__ = ["__version__"]

#: The installed Atlas version. Hatchling reads this value as the single source
#: of truth for the distribution version (see ``[tool.hatch.version]``).
__version__ = "0.0.0"
