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

from typing import TYPE_CHECKING

import typer

from atlas.cli.console import console, error_console, print_json_line
from atlas.cli.doctor import render_report, run_doctor
from atlas.cli.profile import (
    apply_profile_edit,
    build_profile_report,
    load_profile_answers,
    persist_onboarding,
    persist_profile,
    render_profiles,
    switch_active_profile,
)
from atlas.config.errors import ConfigError
from atlas.config.loader import load_config
from atlas.config.secrets import default_secret_store
from atlas.db import initialize_database, session_scope
from atlas.logging import setup_logging
from atlas.profiles.errors import ProfileNotFoundError
from atlas.profiles.onboarding import ask_profile, run_onboarding
from atlas.profiles.prompt import RichPrompter

if TYPE_CHECKING:
    from sqlalchemy.engine import Engine

__all__ = ["app"]

app = typer.Typer(
    name="atlas",
    help="Atlas — a local-first, terminal-native job-application co-pilot.",
    no_args_is_help=True,
    add_completion=False,
)

profile_app = typer.Typer(
    name="profile",
    help="Create, list, edit, and switch search profiles.",
    no_args_is_help=True,
)
app.add_typer(profile_app)


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


def _open_database() -> Engine:
    """Migrate the database to head and return an engine, or exit on failure.

    Wraps :func:`atlas.db.initialize_database` so a migration failure is reported
    on the stderr console (secret-/path-free) and mapped to exit code ``1``
    rather than dumping a traceback. The caller owns the returned engine and must
    dispose it.
    """
    try:
        return initialize_database()
    except Exception as exc:
        # Normalize any bootstrap failure (e.g. MigrationError) to a clean CLI
        # error + exit code, rather than dumping a traceback at the user.
        error_console.print(f"[error]atlas:[/error] could not open the database: {exc}")
        raise typer.Exit(code=1) from exc


@app.command()
def init() -> None:
    """Run first-time onboarding: capture your details and first search profile.

    Walks the onboarding Q&A (PROJECT.md §5.2), then stores the single user
    record and a first, active profile. Master-resume ingest and AI-backend
    selection are separate steps and are not part of this command yet.
    """
    result = run_onboarding(RichPrompter(console))
    engine = _open_database()
    try:
        with session_scope(engine) as session:
            profile_id = persist_onboarding(session, result)
    finally:
        engine.dispose()
    console.print(
        f"[success]Created profile[/success] [accent]{result.profile.name}[/accent] "
        f"(id {profile_id}). You're all set — run [accent]atlas doctor[/accent] to check "
        "your AI backend."
    )


@profile_app.command("list")
def profile_list(
    as_json: bool = typer.Option(
        False,
        "--json",
        help="Emit the profile list as JSON for scripting instead of text.",
    ),
) -> None:
    """List every search profile, marking the active one."""
    engine = _open_database()
    try:
        with session_scope(engine) as session:
            report = build_profile_report(session)
    finally:
        engine.dispose()
    if as_json:
        print_json_line(report.model_dump_json(indent=2))
    else:
        console.print(render_profiles(report))


@profile_app.command("add")
def profile_add() -> None:
    """Create an additional search profile via the preferences Q&A.

    The new profile becomes the active one (the single-active invariant).
    """
    answers = ask_profile(RichPrompter(console))
    engine = _open_database()
    try:
        with session_scope(engine) as session:
            profile_id = persist_profile(session, answers, active=True)
    finally:
        engine.dispose()
    console.print(
        f"[success]Created profile[/success] [accent]{answers.name}[/accent] "
        f"(id {profile_id}) and made it active."
    )


@profile_app.command("edit")
def profile_edit(
    profile_id: int = typer.Argument(..., help="The id of the profile to edit."),
) -> None:
    """Edit an existing profile; current values are offered as defaults."""
    engine = _open_database()
    try:
        with session_scope(engine) as session:
            existing = load_profile_answers(session, profile_id)
        answers = ask_profile(RichPrompter(console), existing=existing)
        with session_scope(engine) as session:
            apply_profile_edit(session, profile_id, answers)
    except ProfileNotFoundError as exc:
        error_console.print(f"[error]atlas profile edit:[/error] {exc}")
        raise typer.Exit(code=1) from exc
    finally:
        engine.dispose()
    console.print(f"[success]Updated profile[/success] [accent]{answers.name}[/accent].")


@profile_app.command("use")
def profile_use(
    profile_id: int = typer.Argument(..., help="The id of the profile to activate."),
) -> None:
    """Make a profile the active one (the single-active invariant)."""
    engine = _open_database()
    try:
        with session_scope(engine) as session:
            switch_active_profile(session, profile_id)
    except ProfileNotFoundError as exc:
        error_console.print(f"[error]atlas profile use:[/error] {exc}")
        raise typer.Exit(code=1) from exc
    finally:
        engine.dispose()
    console.print(f"[success]Activated profile[/success] (id {profile_id}).")
