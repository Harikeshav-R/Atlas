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

from atlas.cli.console import console, error_console, print_json_line
from atlas.cli.doctor import render_report, run_doctor
from atlas.config.errors import ConfigError
from atlas.config.loader import load_config
from atlas.config.secrets import default_secret_store
from atlas.logging import setup_logging

__all__ = ["app"]

app = typer.Typer(
    name="atlas",
    help="Atlas — a local-first, terminal-native job-application co-pilot.",
    no_args_is_help=True,
    add_completion=False,
)


@app.callback()
def main(
    verbose: int = typer.Option(
        0,
        "--verbose",
        "-v",
        count=True,
        help="Increase log verbosity (-v for INFO, -vv for DEBUG).",
    ),
    log_level: str | None = typer.Option(
        None,
        "--log-level",
        help="Explicit console log level (e.g. DEBUG, INFO); overrides -v.",
    ),
) -> None:
    """Atlas command-line interface.

    Runs before every subcommand: it initializes logging (console + rotating log
    file under the state dir) so the level is set no matter which command runs.
    The console level follows ``--log-level`` > ``-v``/``-vv`` >
    ``ATLAS_LOG_LEVEL`` > the ``[logging]`` config > the default; a config that
    fails to load here is tolerated (logging falls back to defaults) so the
    subcommand can surface the real configuration error.
    """
    try:
        logging_config = load_config().logging
    except ConfigError:
        # Don't let a bad config file break logging setup; the invoked command
        # (e.g. `doctor`) reloads config and reports the error properly.
        setup_logging(log_level=log_level, verbose=verbose)
    else:
        setup_logging(
            log_level=log_level,
            verbose=verbose,
            config_level=logging_config.level,
            file_enabled=logging_config.file_enabled,
            max_bytes=logging_config.max_bytes,
            backup_count=logging_config.backup_count,
        )


@app.command()
def doctor(
    as_json: bool = typer.Option(
        False,
        "--json",
        help="Emit the report as JSON for scripting instead of text.",
    ),
    probe: bool = typer.Option(
        False,
        "--probe",
        help="Run a live capability probe (makes a billable call per backend); "
        "reuses cached results where available.",
    ),
    refresh: bool = typer.Option(
        False,
        "--refresh",
        help="With --probe, re-probe every backend, ignoring cached results.",
    ),
) -> None:
    """Validate configuration and report each AI backend's availability.

    By default this makes no model calls and shows cached capabilities when
    present. Pass ``--probe`` to run a live "reply OK as JSON" round-trip against
    each backend (billable) and cache the results; ``--refresh`` forces a
    re-probe. Exit code is ``0`` when at least one backend is usable and ``1``
    when none is (or configuration/secret storage could not be loaded), so
    scripts can gate on ``atlas doctor``.
    """
    try:
        config = load_config()
        store = default_secret_store()
    except ConfigError as exc:
        # Configuration or keyring is unusable — report generically and fail.
        error_console.print(f"[error]atlas doctor:[/error] {exc}")
        raise typer.Exit(code=1) from exc

    report = run_doctor(config.ai, store, probe=probe or refresh, refresh=refresh)
    if as_json:
        print_json_line(report.model_dump_json(indent=2))
    else:
        console.print(render_report(report))
    if not report.healthy:
        raise typer.Exit(code=1)
