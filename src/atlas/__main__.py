"""Entry point for ``python -m atlas`` and the ``atlas`` console script.

Delegates to the Typer application in :mod:`atlas.cli`. Kept trivial so both the
module form (``python -m atlas``) and the installed ``atlas`` script (see
``[project.scripts]`` in ``pyproject.toml``) share one launch path.
"""

from __future__ import annotations

from atlas.cli import app


def main() -> None:
    """Run the Atlas Typer application."""
    app()


if __name__ == "__main__":  # pragma: no cover - exercised only as a script entry point
    main()
