"""Atlas command-line interface (Typer).

The scriptable CLI surface (PROJECT.md §9): a Typer command group whose thin
command functions delegate to Atlas's core logic. This package ships the app
(:data:`atlas.cli.app.app`) and the ``atlas doctor`` command; further commands
(``config``, ``init``, the TUI launcher, …) arrive in later phases.
"""

from __future__ import annotations

from atlas.cli.main import app

__all__ = ["app"]
