"""The Atlas Typer application and its commands.

This is the scriptable CLI surface (PROJECT.md §9). The app is a multi-command
Typer group; a top-level callback keeps it in multi-command mode so subcommands
(``doctor`` today; ``config``, ``init``, … later) route correctly. Command
functions stay thin — they resolve config/secrets, delegate to pure logic (e.g.
:func:`atlas.cli.doctor.run_doctor`), render output, and map failures to exit
codes — so the logic underneath is testable without invoking the CLI.

The module is named ``main`` (not ``app``) so it never collides with the
re-exported :data:`app` Typer instance in :mod:`atlas.cli`.
"""

from __future__ import annotations

import typer

from atlas.cli.doctor import render_report, run_doctor
from atlas.config.errors import ConfigError
from atlas.config.loader import load_config
from atlas.config.secrets import default_secret_store

__all__ = ["app"]

app = typer.Typer(
    name="atlas",
    help="Atlas — a local-first, terminal-native job-application co-pilot.",
    no_args_is_help=True,
    add_completion=False,
)


@app.callback()
def main() -> None:
    """Atlas command-line interface.

    Present so the app stays a multi-command group (subcommands route by name).
    """


@app.command()
def doctor(
    as_json: bool = typer.Option(
        False,
        "--json",
        help="Emit the report as JSON for scripting instead of text.",
    ),
) -> None:
    """Validate configuration and report each AI backend's availability.

    Exit code is ``0`` when at least one backend is usable and ``1`` when none
    is (or configuration/secret storage could not be loaded), so scripts can
    gate on ``atlas doctor``.
    """
    try:
        config = load_config()
        store = default_secret_store()
    except ConfigError as exc:
        # Configuration or keyring is unusable — report generically and fail.
        typer.echo(f"atlas doctor: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    report = run_doctor(config.ai, store)
    typer.echo(report.model_dump_json(indent=2) if as_json else render_report(report))
    if not report.healthy:
        raise typer.Exit(code=1)
