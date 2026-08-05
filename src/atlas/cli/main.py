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

import logging
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, NamedTuple
from urllib.parse import urlsplit

import typer

from atlas.ai.base import LLMError
from atlas.ai.router import build_provider_chain
from atlas.cli.console import console, error_console, print_json_line
from atlas.cli.coverletter import render_cover_letter_outcome
from atlas.cli.daemon import render_daemon_status
from atlas.cli.discovery import (
    build_saved_search_report,
    build_watchlist_report,
    render_discovery_outcome,
    render_saved_searches,
    render_watchlist,
)
from atlas.cli.doctor import build_aggregator_health, render_report, run_doctor
from atlas.cli.matching import render_score
from atlas.cli.materials import render_open_outcome, render_rerender_outcome
from atlas.cli.profile import (
    apply_profile_edit,
    build_profile_report,
    load_profile_answers,
    persist_onboarding,
    persist_profile,
    render_profiles,
    switch_active_profile,
)
from atlas.cli.render import render_render_outcome
from atlas.cli.resume import (
    build_resume_report,
    ingest_resume,
    render_resume_status,
    reparse_resume,
)
from atlas.cli.scrape import (
    build_posting_detail,
    build_postings_report,
    render_posting_detail,
    render_postings,
)
from atlas.cli.tailor import render_tailor_outcome
from atlas.cli.tracking import (
    build_applications_report,
    render_applications,
    render_status_change,
)
from atlas.config.errors import ConfigError
from atlas.config.loader import load_config
from atlas.config.paths import pid_file
from atlas.config.secrets import default_secret_store
from atlas.coverletter.errors import CoverLetterError
from atlas.coverletter.service import write_application_cover_letter
from atlas.daemon.errors import DaemonAlreadyRunningError, DaemonNotRunningError
from atlas.daemon.poll import run_scoring_poll
from atlas.daemon.scheduler import default_scheduler
from atlas.daemon.service import daemon_status, start_daemon, stop_daemon
from atlas.db import initialize_database, session_scope
from atlas.discovery.aggregators import (
    AGGREGATOR_TYPES,
    SavedSearch,
    aggregator_requires_key,
    credential_prompts,
    validate_aggregator,
)
from atlas.discovery.ats import ATS_TYPES, detect_ats
from atlas.discovery.errors import UnknownAggregatorError
from atlas.discovery.poller import DiscoveryOutcome, run_aggregator_poll, run_discovery_poll
from atlas.discovery.service import add_saved_search, add_watchlist_company
from atlas.logging import setup_logging
from atlas.matching.errors import MatchingError, NoActiveProfileError
from atlas.matching.service import ScoreOutcome, score_posting
from atlas.materials.service import open_application, rerender_application
from atlas.platform.opener import FileOpenError, default_file_opener
from atlas.profiles.errors import ProfileNotFoundError
from atlas.profiles.onboarding import ask_profile, run_onboarding
from atlas.profiles.prompt import RichPrompter
from atlas.profiles.repository import get_active_profile, get_profile
from atlas.render.errors import RenderError
from atlas.render.renderer import build_renderer
from atlas.render.service import render_master_resume
from atlas.resume.errors import MasterResumeNotFoundError, ResumeSourceError
from atlas.scrape.errors import JobPostingNotFoundError, ScrapeError
from atlas.scrape.fetcher import default_fetcher
from atlas.scrape.service import AddOutcome, add_posting
from atlas.tailor.errors import ApplicationNotFoundError, TailoringError
from atlas.tailor.service import tailor_posting
from atlas.tracking.errors import InvalidStatusTransitionError
from atlas.tracking.service import mark_applied, set_application_status
from atlas.tracking.status import ApplicationStatus

if TYPE_CHECKING:
    from sqlalchemy.engine import Engine

    from atlas.ai.base import LLMProvider
    from atlas.config.schema import RenderConfig, TailoringConfig
    from atlas.render.renderer import PdfRenderer

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

resume_app = typer.Typer(
    name="resume",
    help="Ingest, reparse, and inspect your master resume.",
    no_args_is_help=True,
)
app.add_typer(resume_app)

postings_app = typer.Typer(
    name="postings",
    help="List and inspect scraped job postings.",
    no_args_is_help=True,
)
app.add_typer(postings_app)

apply_app = typer.Typer(
    name="apply",
    help="Record application submissions.",
    no_args_is_help=True,
)
app.add_typer(apply_app)

status_app = typer.Typer(
    name="status",
    help="Move an application through its pipeline stages.",
    no_args_is_help=True,
)
app.add_typer(status_app)

daemon_app = typer.Typer(
    name="daemon",
    help="Run and control the background scheduler.",
    no_args_is_help=True,
)
app.add_typer(daemon_app)

company_app = typer.Typer(
    name="company",
    help="Manage the ATS company watchlist.",
    no_args_is_help=True,
)
app.add_typer(company_app)

source_app = typer.Typer(
    name="source",
    help="Manage aggregator saved keyword searches.",
    no_args_is_help=True,
)
app.add_typer(source_app)


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
    report.aggregators = build_aggregator_health(config.aggregators, store)
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


def _quiet_console_logging() -> None:
    """Remove the ``atlas`` logger's console handler before the TUI takes over.

    The top-level callback installs a :class:`~rich.logging.RichHandler` on the
    stderr console; left in place it would paint over the Textual display. The
    rotating file handler (a :class:`~logging.FileHandler`) is kept, so DEBUG logs
    still land on disk while the app runs.
    """
    atlas_logger = logging.getLogger("atlas")
    for handler in list(atlas_logger.handlers):
        if not isinstance(handler, logging.FileHandler):
            atlas_logger.removeHandler(handler)


class _TuiActions(NamedTuple):
    """The Tailor-workspace action boundaries, or ``None`` when unavailable.

    Built best-effort by :func:`_build_tui_actions`: when the AI backend or the
    renderer can't be constructed (e.g. no key, bad config), the fields are
    ``None`` and the TUI launches browse-only.
    """

    provider: LLMProvider | None
    renderer: PdfRenderer | None
    tailoring: TailoringConfig | None
    render_config: RenderConfig | None


def _build_tui_actions() -> _TuiActions:
    """Build the Tailor-workspace boundaries, or all-``None`` if they can't be built.

    Replicates the ``atlas tailor`` construction (config → secret store → provider
    chain + renderer). Any configuration/AI/render failure is swallowed to a hint
    on the stderr console so the TUI still opens for browsing (the read/track
    screens need no AI); the Tailor actions are disabled until the backend works.
    """
    try:
        config = load_config()
        store = default_secret_store()
        provider = build_provider_chain(config.ai, store)
        renderer = build_renderer(config.render)
    except (ConfigError, RenderError, LLMError) as exc:
        error_console.print(
            f"[warning]atlas tui:[/warning] AI actions disabled ({exc}); "
            "run [accent]atlas doctor[/accent] to fix your backend."
        )
        return _TuiActions(None, None, None, None)
    return _TuiActions(provider, renderer, config.tailoring, config.render)


@app.command()
def tui() -> None:
    """Launch the interactive Atlas TUI (PROJECT.md §8).

    Opens the Dashboard, Applications (table + Kanban), Application-detail,
    Posting-detail, and Tailor-workspace screens over your saved data. The AI/render
    boundaries the Tailor workspace needs are built best-effort — if they can't be
    (e.g. no key configured) the TUI still opens for browsing and those actions are
    disabled. The app owns the database for its session; console logging is quieted
    first so log records don't corrupt the display (file logging continues).
    """
    engine = _open_database()
    actions = _build_tui_actions()
    _quiet_console_logging()
    from atlas.tui.app import AtlasApp

    app_instance = AtlasApp(
        engine=engine,
        provider=actions.provider,
        renderer=actions.renderer,
        tailoring=actions.tailoring,
        render_config=actions.render_config,
    )
    try:
        app_instance.run()  # pragma: no cover - launches the interactive Textual app
    finally:
        engine.dispose()


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


@resume_app.command("set")
def resume_set(
    path: Path = typer.Argument(
        ...,
        help="Path to the master-resume Markdown file to ingest.",
        exists=False,  # missing files are reported by us, not by Typer, for a themed error
    ),
) -> None:
    """Ingest a Markdown master resume, versioning it when the content changed.

    Reads the file, parses it into content-ID'd blocks, and stores it as a new
    version — unless the content is unchanged from the current version, in which
    case nothing is written (PROJECT.md §5.3). Past versions are never modified.
    """
    engine = _open_database()
    try:
        with session_scope(engine) as session:
            outcome = ingest_resume(session, path)
    except ResumeSourceError as exc:
        error_console.print(f"[error]atlas resume set:[/error] {exc}")
        raise typer.Exit(code=1) from exc
    finally:
        engine.dispose()
    if outcome.created:
        console.print(
            f"[success]Saved master resume[/success] (version [accent]{outcome.version}[/accent], "
            f"{outcome.block_count} blocks)."
        )
    else:
        console.print(
            f"[muted]No change — master resume is already at version {outcome.version}.[/muted]"
        )


@resume_app.command("reparse")
def resume_reparse() -> None:
    """Re-parse the current master resume into a new version.

    Re-runs the parser on the latest version's stored Markdown and saves the
    result as a new version, so an improved parser can be applied without the
    original file. Fails if no master resume has been set yet.
    """
    engine = _open_database()
    try:
        with session_scope(engine) as session:
            outcome = reparse_resume(session)
    except MasterResumeNotFoundError as exc:
        error_console.print(f"[error]atlas resume reparse:[/error] {exc}")
        raise typer.Exit(code=1) from exc
    finally:
        engine.dispose()
    console.print(
        f"[success]Reparsed master resume[/success] (version [accent]{outcome.version}[/accent], "
        f"{outcome.block_count} blocks)."
    )


@resume_app.command("render")
def resume_render(
    as_json: bool = typer.Option(
        False,
        "--json",
        help="Emit the render outcome as JSON for scripting instead of text.",
    ),
) -> None:
    """Render the latest master-resume version to a one-page PDF.

    Builds the HTML from the configured theme, renders it to PDF with the
    configured engine (PROJECT.md §5.11), stores the PDF under the data dir, and
    reports the path and measured page count. Rendering is deterministic (no AI).
    Exits ``1`` if configuration is invalid, the render engine is unsupported, or
    no master resume has been set yet.
    """
    try:
        config = load_config()
        renderer = build_renderer(config.render)
    except (ConfigError, RenderError) as exc:
        error_console.print(f"[error]atlas resume render:[/error] {exc}")
        raise typer.Exit(code=1) from exc
    engine = _open_database()
    try:
        with session_scope(engine) as session:
            outcome = render_master_resume(
                session, renderer=renderer, theme=config.render.resume_theme
            )
    except RenderError as exc:
        error_console.print(f"[error]atlas resume render:[/error] {exc}")
        raise typer.Exit(code=1) from exc
    finally:
        engine.dispose()
    if as_json:
        print_json_line(outcome.model_dump_json(indent=2))
    else:
        console.print(render_render_outcome(outcome))


@resume_app.command("show")
def resume_show(
    as_json: bool = typer.Option(
        False,
        "--json",
        help="Emit the version list as JSON for scripting instead of text.",
    ),
) -> None:
    """Show the stored master-resume versions, marking the latest."""
    engine = _open_database()
    try:
        with session_scope(engine) as session:
            report = build_resume_report(session)
    finally:
        engine.dispose()
    if as_json:
        print_json_line(report.model_dump_json(indent=2))
    else:
        console.print(render_resume_status(report))


@app.command()
def add(
    url: str = typer.Argument(..., help="URL of the job posting to scrape and save."),
) -> None:
    """Scrape a job posting from a URL, parse it, save it, and score it for fit.

    Fetches the page, extracts the normalized fields (structured data first, then
    an AI pass over the page text, PROJECT.md §5.5), stores a raw snapshot, and
    persists the posting. Re-adding a URL already saved is a no-op. A newly saved
    posting is then scored for fit (PROJECT.md §5.6); scoring runs in its own
    transaction so a scoring failure (e.g. no profile/resume yet) never discards
    the saved posting — it just prints a hint to run ``atlas score`` later.
    """
    try:
        config = load_config()
        store = default_secret_store()
    except ConfigError as exc:
        error_console.print(f"[error]atlas add:[/error] {exc}")
        raise typer.Exit(code=1) from exc
    provider = build_provider_chain(config.ai, store)
    engine = _open_database()
    try:
        with session_scope(engine) as session:
            outcome = add_posting(session, url, provider=provider)
        score = _score_after_add(engine, outcome, provider=provider) if outcome.created else None
    except ScrapeError as exc:
        error_console.print(f"[error]atlas add:[/error] {exc}")
        raise typer.Exit(code=1) from exc
    finally:
        engine.dispose()
    if outcome.created:
        message = (
            f"[success]Saved posting[/success] [accent]{outcome.title}[/accent] "
            f"@ {outcome.company} (id {outcome.posting_id})."
        )
        if score is not None:
            message += f" [muted]Fit:[/muted] [accent]{score.score}[/accent] {score.verdict}."
        console.print(message)
    else:
        console.print(
            f"[muted]Already added — [/muted][accent]{outcome.title}[/accent]"
            f"[muted] @ {outcome.company} (id {outcome.posting_id}).[/muted]"
        )


def _score_after_add(
    engine: Engine, outcome: AddOutcome, *, provider: LLMProvider
) -> ScoreOutcome | None:
    """Score a freshly-added posting against the active profile, best-effort.

    Returns the :class:`~atlas.matching.service.ScoreOutcome` on success, or
    ``None`` when scoring can't run yet (no active profile / no master resume) or
    the AI backend fails — printing a muted hint rather than failing ``atlas add``,
    since the posting is already saved.
    """
    try:
        with session_scope(engine) as session:
            profile = get_active_profile(session)
            if profile is None:
                raise NoActiveProfileError
            return score_posting(session, outcome.posting_id, profile=profile, provider=provider)
    except MatchingError as exc:
        console.print(
            f"[muted]Saved, but not scored — {exc} Run `atlas score {outcome.posting_id}`.[/muted]"
        )
        return None


@app.command()
def score(
    posting_id: int = typer.Argument(..., help="The id of the saved posting to score."),
    profile_id: int | None = typer.Option(
        None, "--profile", help="Score against this profile id (defaults to the active profile)."
    ),
    as_json: bool = typer.Option(
        False,
        "--json",
        help="Emit the fit assessment as JSON for scripting instead of text.",
    ),
) -> None:
    """Score a saved posting for fit against a profile (the active one by default).

    Sends the posting, the profile's preferences, a compact master-resume summary,
    and Atlas's deterministic signals to the AI and records a fit assessment
    (PROJECT.md §5.6). Pass ``--profile`` to score against a specific profile rather
    than the active one (each profile keeps its own score history). Re-scoring
    appends a new assessment rather than replacing the last one. Exits ``1`` if the
    posting or profile id is unknown, no profile is active, no master resume is set,
    or the AI cannot produce an assessment.
    """
    try:
        config = load_config()
        store = default_secret_store()
    except ConfigError as exc:
        error_console.print(f"[error]atlas score:[/error] {exc}")
        raise typer.Exit(code=1) from exc
    provider = build_provider_chain(config.ai, store)
    engine = _open_database()
    try:
        with session_scope(engine) as session:
            if profile_id is not None:
                profile = get_profile(session, profile_id)
            else:
                active = get_active_profile(session)
                if active is None:
                    raise NoActiveProfileError
                profile = active
            outcome = score_posting(session, posting_id, profile=profile, provider=provider)
    except (JobPostingNotFoundError, ProfileNotFoundError, MatchingError) as exc:
        error_console.print(f"[error]atlas score:[/error] {exc}")
        raise typer.Exit(code=1) from exc
    finally:
        engine.dispose()
    if as_json:
        print_json_line(outcome.model_dump_json(indent=2))
    else:
        console.print(render_score(outcome))


@app.command()
def tailor(
    job_id: int = typer.Argument(..., help="The id of the saved posting to tailor for."),
    as_json: bool = typer.Option(
        False,
        "--json",
        help="Emit the tailoring outcome as JSON for scripting instead of text.",
    ),
) -> None:
    """Tailor your resume to a saved posting and render it to a one-page PDF.

    An honesty-governed AI pass selects and rewords the most relevant master-resume
    content for the posting (every item traceable to a source block), a
    deterministic safety net restores dropped dates, and a render-measure-trim loop
    packs the result to one page (PROJECT.md §5.7). The tailored resume is saved
    under an application for the posting and rendered to a PDF. Exits ``1`` if the
    posting id is unknown, no profile is active, no master resume is set, config or
    the render engine is invalid, or the AI cannot produce a tailored resume.
    """
    try:
        config = load_config()
        store = default_secret_store()
        provider = build_provider_chain(config.ai, store)
        renderer = build_renderer(config.render)
    except (ConfigError, RenderError) as exc:
        error_console.print(f"[error]atlas tailor:[/error] {exc}")
        raise typer.Exit(code=1) from exc
    engine = _open_database()
    try:
        with session_scope(engine) as session:
            outcome = tailor_posting(
                session,
                job_id,
                provider=provider,
                renderer=renderer,
                honesty_level=config.tailoring.honesty_level.value,
                theme=config.render.resume_theme,
                enforce_one_page=config.tailoring.enforce_one_page,
            )
    except (JobPostingNotFoundError, TailoringError) as exc:
        error_console.print(f"[error]atlas tailor:[/error] {exc}")
        raise typer.Exit(code=1) from exc
    finally:
        engine.dispose()
    if as_json:
        print_json_line(outcome.model_dump_json(indent=2))
    else:
        console.print(render_tailor_outcome(outcome))


@app.command()
def cover(
    job_id: int = typer.Argument(..., help="The id of the saved posting to write a letter for."),
    tone: str = typer.Option("professional", "--tone", help="The tone to write the letter in."),
    as_json: bool = typer.Option(
        False,
        "--json",
        help="Emit the cover-letter outcome as JSON for scripting instead of text.",
    ),
) -> None:
    """Write a cover letter for a saved posting and render it to a PDF.

    An honesty-governed AI pass drafts a structured letter grounded in the
    application's tailored resume (or the master resume) and the posting
    (PROJECT.md §5.8), rendered to a PDF matching the resume styling. Exits ``1``
    if the posting id is unknown, no profile is active, there is no resume to
    ground the letter in, config/render engine is invalid, or the AI cannot
    produce a letter.
    """
    try:
        config = load_config()
        store = default_secret_store()
        provider = build_provider_chain(config.ai, store)
        renderer = build_renderer(config.render)
    except (ConfigError, RenderError) as exc:
        error_console.print(f"[error]atlas cover:[/error] {exc}")
        raise typer.Exit(code=1) from exc
    engine = _open_database()
    try:
        with session_scope(engine) as session:
            outcome = write_application_cover_letter(
                session,
                job_id,
                provider=provider,
                renderer=renderer,
                honesty_level=config.tailoring.honesty_level.value,
                theme=config.render.cover_theme,
                tone=tone,
            )
    except (JobPostingNotFoundError, CoverLetterError) as exc:
        error_console.print(f"[error]atlas cover:[/error] {exc}")
        raise typer.Exit(code=1) from exc
    finally:
        engine.dispose()
    if as_json:
        print_json_line(outcome.model_dump_json(indent=2))
    else:
        console.print(render_cover_letter_outcome(outcome))


@app.command()
def render(
    application_id: int = typer.Argument(..., help="The id of the application to re-render."),
    as_json: bool = typer.Option(
        False,
        "--json",
        help="Emit the re-render outcome as JSON for scripting instead of text.",
    ),
) -> None:
    """Re-render an application's materials (tailored resume + cover letter) to PDFs.

    Regenerates the PDFs deterministically from each material's stored content —
    no AI call (PROJECT.md §9, §5.11). Whichever material the application does not
    have yet is skipped. Exits ``1`` if the application id is unknown or the render
    engine is unavailable.
    """
    try:
        config = load_config()
        renderer = build_renderer(config.render)
    except (ConfigError, RenderError) as exc:
        error_console.print(f"[error]atlas render:[/error] {exc}")
        raise typer.Exit(code=1) from exc
    engine = _open_database()
    try:
        with session_scope(engine) as session:
            outcome = rerender_application(
                session,
                application_id,
                renderer=renderer,
                resume_theme=config.render.resume_theme,
                cover_theme=config.render.cover_theme,
            )
    except (ApplicationNotFoundError, RenderError) as exc:
        error_console.print(f"[error]atlas render:[/error] {exc}")
        raise typer.Exit(code=1) from exc
    finally:
        engine.dispose()
    if as_json:
        print_json_line(outcome.model_dump_json(indent=2))
    else:
        console.print(render_rerender_outcome(outcome))


@app.command(name="open")
def open_materials(
    application_id: int = typer.Argument(..., help="The id of the application to open."),
    as_json: bool = typer.Option(
        False,
        "--json",
        help="Emit the open outcome as JSON for scripting instead of text.",
    ),
) -> None:
    """Open an application's exported PDFs in the OS default viewer.

    Opens the latest rendered tailored-resume and cover-letter PDFs (PROJECT.md
    §9). Exits ``1`` if the application id is unknown or a referenced PDF cannot be
    opened.
    """
    engine = _open_database()
    try:
        with session_scope(engine) as session:
            outcome = open_application(session, application_id, opener=default_file_opener)
    except (ApplicationNotFoundError, FileOpenError) as exc:
        error_console.print(f"[error]atlas open:[/error] {exc}")
        raise typer.Exit(code=1) from exc
    finally:
        engine.dispose()
    if as_json:
        print_json_line(outcome.model_dump_json(indent=2))
    else:
        console.print(render_open_outcome(outcome))


@postings_app.command("list")
def postings_list(
    as_json: bool = typer.Option(
        False,
        "--json",
        help="Emit the posting list as JSON for scripting instead of text.",
    ),
) -> None:
    """List every saved job posting."""
    engine = _open_database()
    try:
        with session_scope(engine) as session:
            report = build_postings_report(session)
    finally:
        engine.dispose()
    if as_json:
        print_json_line(report.model_dump_json(indent=2))
    else:
        console.print(render_postings(report))


@postings_app.command("show")
def postings_show(
    posting_id: int = typer.Argument(..., help="The id of the posting to show."),
    as_json: bool = typer.Option(
        False,
        "--json",
        help="Emit the posting as JSON for scripting instead of text.",
    ),
) -> None:
    """Show one saved posting's normalized fields."""
    engine = _open_database()
    try:
        with session_scope(engine) as session:
            detail = build_posting_detail(session, posting_id)
    except JobPostingNotFoundError as exc:
        error_console.print(f"[error]atlas postings show:[/error] {exc}")
        raise typer.Exit(code=1) from exc
    finally:
        engine.dispose()
    if as_json:
        print_json_line(detail.model_dump_json(indent=2))
    else:
        console.print(render_posting_detail(detail))


@apply_app.command("mark")
def apply_mark(
    application_id: int = typer.Argument(..., help="The id of the application to mark applied."),
    force: bool = typer.Option(
        False,
        "--force",
        help="Bypass the state machine and allow the transition from any stage.",
    ),
    as_json: bool = typer.Option(
        False,
        "--json",
        help="Emit the status change as JSON for scripting instead of text.",
    ),
) -> None:
    """Mark an application submitted, recording the applied date (PROJECT.md §9).

    Moves the application to the ``applied`` stage and stamps ``applied_at``.
    Exits ``1`` if the application id is unknown, or if it cannot reach ``applied``
    from its current stage (pass ``--force`` to override the state machine).
    """
    engine = _open_database()
    try:
        with session_scope(engine) as session:
            outcome = mark_applied(session, application_id, force=force)
    except (ApplicationNotFoundError, InvalidStatusTransitionError) as exc:
        error_console.print(f"[error]atlas apply mark:[/error] {exc}")
        raise typer.Exit(code=1) from exc
    finally:
        engine.dispose()
    if as_json:
        print_json_line(outcome.model_dump_json(indent=2))
    else:
        console.print(render_status_change(outcome))


@status_app.command("set")
def status_set(
    application_id: int = typer.Argument(..., help="The id of the application to transition."),
    stage: ApplicationStatus = typer.Argument(..., help="The pipeline stage to move to."),
    due: datetime | None = typer.Option(
        None,
        "--due",
        help="An advisory deadline to record with the transition (e.g. an OA/interview date).",
    ),
    force: bool = typer.Option(
        False,
        "--force",
        help="Bypass the state machine and allow the transition from any stage.",
    ),
    as_json: bool = typer.Option(
        False,
        "--json",
        help="Emit the status change as JSON for scripting instead of text.",
    ),
) -> None:
    """Move an application to a pipeline stage (PROJECT.md §9, §5.12).

    Records the transition in the application's status history (with the optional
    ``--due`` deadline) and updates the derived fields — ``applied_at`` on reaching
    ``applied``, ``outcome`` on reaching a terminal stage. Exits ``1`` if the
    application id is unknown, or if the move is not a permitted transition (pass
    ``--force`` to override the state machine).
    """
    engine = _open_database()
    try:
        with session_scope(engine) as session:
            outcome = set_application_status(session, application_id, stage, force=force, due=due)
    except (ApplicationNotFoundError, InvalidStatusTransitionError) as exc:
        error_console.print(f"[error]atlas status set:[/error] {exc}")
        raise typer.Exit(code=1) from exc
    finally:
        engine.dispose()
    if as_json:
        print_json_line(outcome.model_dump_json(indent=2))
    else:
        console.print(render_status_change(outcome))


@app.command(name="list")
def list_applications_command(
    status: ApplicationStatus | None = typer.Option(
        None,
        "--status",
        help="Show only applications currently in this stage.",
    ),
    profile_id: int | None = typer.Option(
        None,
        "--profile",
        help="Show only applications prepared under this profile id.",
    ),
    as_json: bool = typer.Option(
        False,
        "--json",
        help="Emit the application list as JSON for scripting instead of text.",
    ),
) -> None:
    """List tracked applications, most recently updated first (PROJECT.md §9).

    Optionally filter by ``--status`` (pipeline stage) or ``--profile`` (the
    profile the application was prepared under).
    """
    engine = _open_database()
    try:
        with session_scope(engine) as session:
            report = build_applications_report(session, status=status, profile_id=profile_id)
    finally:
        engine.dispose()
    if as_json:
        print_json_line(report.model_dump_json(indent=2))
    else:
        console.print(render_applications(report))


@daemon_app.command("start")
def daemon_start() -> None:
    """Start the background scheduler (foreground, blocking) (PROJECT.md §4.1, §9).

    Runs Atlas's scheduled work on the ``[discovery]`` ``poll_interval_minutes``
    interval: first a **discovery poll** over the enabled ATS watchlist (fetching
    and persisting new postings), then a **scoring poll** that clears the fit-score
    backlog — including whatever discovery just added — against the active profile.
    This blocks the terminal until stopped (``atlas daemon stop`` or Ctrl-C);
    background it with your OS service manager. Exits ``1`` if config/secrets can't
    load or a daemon is already running.
    """
    try:
        config = load_config()
        store = default_secret_store()
    except ConfigError as exc:
        error_console.print(f"[error]atlas daemon start:[/error] {exc}")
        raise typer.Exit(code=1) from exc
    provider = build_provider_chain(config.ai, store)
    engine = _open_database()

    def run() -> None:
        """Run discovery + aggregator polls, then score the backlog.

        Each poll runs in its own short transaction and commits its new postings
        first, so the scoring poll's ``list_unscored_postings`` picks them all up on
        the same tick.
        """
        with session_scope(engine) as session:
            run_discovery_poll(session, fetcher=default_fetcher)
        with session_scope(engine) as session:
            run_aggregator_poll(
                session, config=config.aggregators, store=store, fetcher=default_fetcher
            )
        with session_scope(engine) as session:
            run_scoring_poll(session, provider=provider)

    try:
        start_daemon(
            pid_file(),
            config.discovery,
            scheduler=default_scheduler(),
            run=run,
        )
    except DaemonAlreadyRunningError as exc:
        error_console.print(f"[error]atlas daemon start:[/error] {exc}")
        raise typer.Exit(code=1) from exc
    finally:
        engine.dispose()


@daemon_app.command("stop")
def daemon_stop() -> None:
    """Stop the running background scheduler (PROJECT.md §9).

    Signals the daemon process to shut down and clears its PID file. Exits ``1``
    if no daemon is running.
    """
    try:
        pid = stop_daemon(pid_file())
    except DaemonNotRunningError as exc:
        error_console.print(f"[error]atlas daemon stop:[/error] {exc}")
        raise typer.Exit(code=1) from exc
    console.print(f"[success]Stopped the daemon[/success] (pid {pid}).")


@daemon_app.command("status")
def daemon_status_command(
    as_json: bool = typer.Option(
        False,
        "--json",
        help="Emit the daemon status as JSON for scripting instead of text.",
    ),
) -> None:
    """Report whether the background scheduler is running (PROJECT.md §9)."""
    status = daemon_status(pid_file())
    if as_json:
        print_json_line(status.model_dump_json(indent=2))
    else:
        console.print(render_daemon_status(status))


def _display_name_from_token(token: str) -> str:
    """Derive a human-ish company name from a board token (``"acme-corp"`` → ``"Acme Corp"``)."""
    return token.replace("-", " ").replace("_", " ").title()


@company_app.command("add")
def company_add(
    url: str = typer.Argument(..., help="A careers/board URL (the ATS is auto-detected)."),
    name: str | None = typer.Option(
        None, "--name", help="Company display name (defaults to the board token)."
    ),
    as_json: bool = typer.Option(
        False,
        "--json",
        help="Emit the added company as JSON for scripting instead of text.",
    ),
) -> None:
    """Add a company's ATS board to the discovery watchlist (PROJECT.md §5.4, §9).

    Auto-detects the ATS provider and board token from ``url`` (no ``--ats`` flag),
    then records the company and its board so the daemon's discovery poll (and
    ``atlas discover``) fetch it. Re-adding the same board is a no-op. Exits ``1``
    if the URL is not a recognized ATS board.
    """
    detected = detect_ats(url)
    if detected is None:
        supported = ", ".join(ATS_TYPES)
        error_console.print(
            f"[error]atlas company add:[/error] unrecognized ATS URL. "
            f"Supported providers: {supported}."
        )
        raise typer.Exit(code=1)
    ats_type, board_token = detected
    display_name = name or _display_name_from_token(board_token)
    engine = _open_database()
    try:
        with session_scope(engine) as session:
            outcome = add_watchlist_company(
                session,
                name=display_name,
                ats_type=ats_type,
                board_token=board_token,
                domain=urlsplit(url).hostname,
            )
    finally:
        engine.dispose()
    if as_json:
        print_json_line(outcome.model_dump_json(indent=2))
    elif outcome.created:
        console.print(
            f"[success]Watchlisted[/success] [accent]{outcome.name}[/accent] "
            f"({outcome.ats_type}: {outcome.board_token}). "
            "Run [accent]atlas discover[/accent] to poll it now."
        )
    else:
        console.print(
            f"[muted]Already watchlisted — [/muted][accent]{outcome.name}[/accent]"
            f"[muted] ({outcome.ats_type}: {outcome.board_token}).[/muted]"
        )


@company_app.command("list")
def company_list(
    as_json: bool = typer.Option(
        False,
        "--json",
        help="Emit the watchlist as JSON for scripting instead of text.",
    ),
) -> None:
    """List watchlisted ATS boards, newest last (PROJECT.md §9)."""
    engine = _open_database()
    try:
        with session_scope(engine) as session:
            report = build_watchlist_report(session)
    finally:
        engine.dispose()
    if as_json:
        print_json_line(report.model_dump_json(indent=2))
    else:
        console.print(render_watchlist(report))


@app.command()
def discover(
    as_json: bool = typer.Option(
        False,
        "--json",
        help="Emit the discovery outcome as JSON for scripting instead of text.",
    ),
) -> None:
    """Run one discovery poll now over every source (PROJECT.md §5.4, §9).

    Fetches every enabled ATS board **and** aggregator saved search, normalizes and
    persists the new postings (deduplicated), and reports the combined counts.
    Discovery is AI-free — it does not score; run [accent]atlas score[/accent] or the
    daemon (which chains discovery → scoring) to score the newly-found postings.
    """
    try:
        config = load_config()
        store = default_secret_store()
    except ConfigError as exc:
        error_console.print(f"[error]atlas discover:[/error] {exc}")
        raise typer.Exit(code=1) from exc
    engine = _open_database()
    try:
        with session_scope(engine) as session:
            ats_outcome = run_discovery_poll(session, fetcher=default_fetcher)
        with session_scope(engine) as session:
            aggregator_outcome = run_aggregator_poll(
                session, config=config.aggregators, store=store, fetcher=default_fetcher
            )
    finally:
        engine.dispose()
    outcome = DiscoveryOutcome(
        sources_polled=ats_outcome.sources_polled + aggregator_outcome.sources_polled,
        discovered=ats_outcome.discovered + aggregator_outcome.discovered,
        skipped=ats_outcome.skipped + aggregator_outcome.skipped,
        failed_sources=ats_outcome.failed_sources + aggregator_outcome.failed_sources,
        inactive=ats_outcome.inactive + aggregator_outcome.inactive,
    )
    if as_json:
        print_json_line(outcome.model_dump_json(indent=2))
    else:
        console.print(render_discovery_outcome(outcome))
        if outcome.discovered:
            console.print(
                "[muted]Run [/muted][accent]atlas score <id>[/accent]"
                "[muted] (or the daemon) to score the new postings.[/muted]"
            )


@source_app.command("add")
def source_add(
    aggregator: str = typer.Argument(..., help=f"The aggregator ({', '.join(AGGREGATOR_TYPES)})."),
    query: str = typer.Option(..., "--query", "-q", help="Keywords to search for."),
    location: str | None = typer.Option(
        None, "--location", help="Filter results to a location (free text)."
    ),
    remote: bool | None = typer.Option(
        None, "--remote/--onsite", help="Keep only remote (or only on-site) roles."
    ),
    as_json: bool = typer.Option(
        False,
        "--json",
        help="Emit the saved search as JSON for scripting instead of text.",
    ),
) -> None:
    """Add an aggregator saved keyword search for the active profile (PROJECT.md §5.4-B, §9).

    Validates ``aggregator`` against the registered providers, then records the
    search (query + optional location / remote filters) for the active profile so
    the daemon's discovery poll (and ``atlas discover``) run it. Re-adding the same
    search is a no-op. Exits ``1`` if the aggregator is unknown or no profile is
    active yet.
    """
    try:
        validate_aggregator(aggregator)
    except UnknownAggregatorError as exc:
        error_console.print(f"[error]atlas source add:[/error] {exc}")
        raise typer.Exit(code=1) from exc
    spec = SavedSearch(query=query, location=location, remote=remote)
    engine = _open_database()
    try:
        with session_scope(engine) as session:
            profile = get_active_profile(session)
            if profile is None or profile.id is None:
                error_console.print(
                    "[error]atlas source add:[/error] no active profile. "
                    "Run [accent]atlas init[/accent] first."
                )
                raise typer.Exit(code=1)
            outcome = add_saved_search(
                session, aggregator=aggregator, spec=spec, profile_id=profile.id
            )
    finally:
        engine.dispose()
    if as_json:
        print_json_line(outcome.model_dump_json(indent=2))
    elif outcome.created:
        # A key-gated provider stays inactive until its credential is stored.
        next_step = (
            f"Run [accent]atlas source key {outcome.aggregator}[/accent] to add its API key, "
            "then [accent]atlas discover[/accent]."
            if aggregator_requires_key(aggregator)
            else "Run [accent]atlas discover[/accent] to poll it now."
        )
        console.print(
            f"[success]Saved search[/success] [accent]{outcome.aggregator}[/accent] "
            f"({outcome.query!r}). {next_step}"
        )
    else:
        console.print(
            f"[muted]Already saved — [/muted][accent]{outcome.aggregator}[/accent]"
            f"[muted] ({outcome.query!r}).[/muted]"
        )


@source_app.command("key")
def source_key(
    aggregator: str = typer.Argument(
        ..., help="The key-gated aggregator whose credential(s) to store."
    ),
) -> None:
    """Store a key-gated aggregator's API credential(s) in the OS keychain (§5.4-B).

    Prompts for each credential with hidden input (never echoed, never in shell
    history) and writes it to the OS keychain under the handle from config, so the
    daemon and ``atlas discover`` can activate the source. The secret is never
    printed, logged, or stored in config. Exits ``1`` if the aggregator is unknown
    or is a free (no-key) source, or if the keychain is unavailable.
    """
    try:
        validate_aggregator(aggregator)
    except UnknownAggregatorError as exc:
        error_console.print(f"[error]atlas source key:[/error] {exc}")
        raise typer.Exit(code=1) from exc
    if not aggregator_requires_key(aggregator):
        keyed = ", ".join(name for name in AGGREGATOR_TYPES if aggregator_requires_key(name))
        error_console.print(
            f"[error]atlas source key:[/error] [accent]{aggregator}[/accent] needs no API key. "
            f"Key-gated aggregators: {keyed}."
        )
        raise typer.Exit(code=1)
    try:
        config = load_config()
        store = default_secret_store()
    except ConfigError as exc:
        error_console.print(f"[error]atlas source key:[/error] {exc}")
        raise typer.Exit(code=1) from exc
    for prompt in credential_prompts(aggregator, config.aggregators):
        value = typer.prompt(prompt.label, hide_input=True)
        store.set(prompt.handle, value)
    console.print(
        f"[success]Stored credentials[/success] for [accent]{aggregator}[/accent]. "
        f"Enable it in your config's [accent][aggregators.{aggregator}][/accent] section, "
        "then run [accent]atlas discover[/accent]."
    )


@source_app.command("list")
def source_list(
    as_json: bool = typer.Option(
        False,
        "--json",
        help="Emit the saved searches as JSON for scripting instead of text.",
    ),
) -> None:
    """List aggregator saved searches, newest last (PROJECT.md §9)."""
    engine = _open_database()
    try:
        with session_scope(engine) as session:
            report = build_saved_search_report(session)
    finally:
        engine.dispose()
    if as_json:
        print_json_line(report.model_dump_json(indent=2))
    else:
        console.print(render_saved_searches(report))
