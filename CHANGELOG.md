# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- **Desktop notifications** (`atlas.notify` + `atlas.platform.notifier`): the
  daemon now posts native OS notifications for new high-fit matches and upcoming
  deadlines even when the TUI is closed (PROJECT.md §5.16) — the **last Phase-2
  item**, so Phase 2 (Discovery & background) is complete. A `Notifier` platform
  seam mirrors the file/URL openers (a `@runtime_checkable` protocol + a pragma'd
  `default_notifier` over [`desktop-notifier`](https://pypi.org/project/desktop-notifier/)'s
  cross-platform backend — D-Bus / Notification Center / WinRT — degrading
  gracefully). A best-effort `notify_best_effort` (mirroring `emit_progress`) and
  a JSON run-state file under the state dir (mirroring the probe cache) mean a
  dead backend never breaks a poll and a re-poll never re-notifies (a monotonic
  score-id high-water mark for matches, stable per-deadline keys for deadlines).
  New queries: `matching.repository.list_new_high_fit` and
  `tracking.repository.upcoming_deadlines` (scanning `status_history` for advisory
  due dates — no schema change). The `notify_after_poll` orchestrator honors a
  `[notifications]` config section (`enabled` — **ships disabled** — plus
  `min_match_score`, `deadline_lead_hours`, `quiet_hours` with midnight wrap, and
  a `daily_cap`), and is fired after scoring from both the scheduled tick and the
  on-demand IPC poll. No new database migration.
- New runtime dependency: `desktop-notifier` (native OS notifications).
- **Daemon IPC surface** (`atlas.daemon.ipc`): the local socket the TUI/CLI use
  to trigger on-demand daemon work and stream its progress (PROJECT.md §4.1) —
  the last unchecked "Daemon + scheduler + IPC" sub-item. A newline-delimited-JSON
  protocol (an `IpcRequest` with a `"status"` / `"poll"` action and a discriminated
  `IpcEvent` union — `StatusEvent` / `ProgressEvent` / `ResultEvent` / `ErrorEvent`)
  with a pure codec, plus a transport-free `handle_request` core that pushes events
  through an injected `emit`: `"status"` replies with the daemon's run-state;
  `"poll"` runs one discovery + aggregator + scoring pass (reusing the daemon's
  claim owner so an on-demand poll never double-scores against the scheduled tick),
  streaming per-phase progress and a terminal result. Following the
  `platform/opener.py` seam, the framing (server-side `handle_connection`,
  client-side `stream_events` / `ipc_request`) is pure and fully tested against an
  in-memory duplex fake, while only the real socket bind/accept/connect carries a
  justified `# pragma: no cover`. The transport dispatches on `sys.platform`
  (AF_UNIX on POSIX, loopback TCP on Windows — stdlib-only, no new dependency).
  Adds `IpcError` / `IpcProtocolError` / `IpcUnavailableError`.
- **Progress-callback seam on the polls** (`atlas.daemon.progress`): a small
  `ProgressUpdate` model + `ProgressCallback` alias + best-effort `emit_progress`
  helper (a raising sink is logged and swallowed, never breaking the poll). The
  three poll functions (`run_discovery_poll`, `run_aggregator_poll`,
  `run_scoring_poll`) gained an optional `on_progress` param (default `None`, so
  every existing caller is unaffected) that emits start → per-source / per-pair
  item → done, letting the IPC surface stream a poll live.
- **`socket_file()` path helper** (`atlas.config.paths`): the daemon's IPC socket
  path under the state dir (`daemon.socket`), sibling to `pid_file()`.
- **IPC served from the daemon**: `start_daemon` gained optional
  `ipc_server` / `dispatch` / `socket_path` params — when supplied it removes a
  stale socket, serves the IPC surface on a background thread before the blocking
  `scheduler.start()`, and stops it on shutdown. `atlas daemon start` wires this
  up (a `default_ipc_server()` behind an injectable `IpcServer` seam, plus a
  `dispatch` bound to the daemon's engine/config/provider/owner).
- **`atlas daemon poll` command** (PROJECT.md §9): asks the running daemon to poll
  now over IPC, streaming each phase's progress (to stderr, so `--json` on stdout
  stays pipe-safe) and printing the summary; exits `1` on a poll error or when the
  daemon is not running.
- **TUI "poll now" on the Discover screen** (press `g`): triggers the daemon poll
  over IPC in a thread worker, toasting per-phase progress and refreshing the queue
  when it finishes (so newly-scored postings appear). When no daemon socket is
  configured it is a safe warning no-op. `AtlasApp` gained an injected
  `socket_path` and a `run_poll_now` IPC-client method.
- **Multiple profiles fully wired** (`atlas.matching`, `atlas.daemon`, `atlas.tui`):
  scoring and the Discover queue are now **per-profile** rather than
  single-active. The daemon's poll scores **every** profile's backlog each tick
  (PROJECT.md §2.1, §5.6), so each profile has a complete ranked queue the instant
  the user switches to it. The queue and `atlas score` read `match_score.profile_id`
  as a filter (it was written but never read): `list_unscored_postings` /
  `list_scored_postings` are keyed by profile, and `score_posting` takes the profile
  from its caller instead of resolving the active one internally. Includes a **TUI
  profile switcher** on the Discover screen (press `p`), a `atlas score --profile
  <id>` option, and PROJECT.md §4.1's row-level **"owned by" scoring lease**
  (`score_claim`) so a concurrent writer never double-scores. No score-table
  migration (the `profile_id` column already existed).
- **`score_claim` table + `atlas.matching.claims`** (PROJECT.md §4.1): a lightweight
  per-`(posting, profile)` scoring lease with a unique constraint on the pair.
  `try_claim` acquires a fresh pair, refuses a live claim, and steals a stale one
  (past its lease); `release_claim` frees it. The daemon poll claims each pair before
  scoring and releases it after, using its pid as the owner token. Ships with an
  Alembic migration.
- **`atlas score --profile <id>`**: score a saved posting against a specific profile
  rather than the active one (each profile keeps its own append-only score history);
  an unknown profile id exits `1`.
- **`busy_timeout` PRAGMA** (`atlas.db.engine`): every SQLite connection now sets
  `busy_timeout=5000` alongside WAL + foreign keys, so a connection waits briefly for
  a contended write lock instead of failing with "database is locked" — the more so
  now that the daemon scores every profile while the TUI reads (PROJECT.md §4.1, §17).
- **Key-gated aggregator adapters — Adzuna + USAJOBS** (`atlas.discovery.aggregators`):
  the two credential-requiring aggregators PROJECT.md §5.4-B names, joining the
  free RemoteOK/Remotive feeds. **Adzuna** (`api.adzuna.com`) uses query-string
  auth (`app_id` + `app_key` + a configurable country); **USAJOBS**
  (`data.usajobs.gov`) uses header auth (`Authorization-Key` + the registering
  email as `User-Agent`) — the reason the `Fetcher` seam carries a `headers`
  parameter. Each is a drop-in on the registry: a key-gating seam
  (`AggregatorAdapter.requires_key` + a `build_aggregator(name, *, config, store)`
  builder that resolves credentials from the keychain and returns `None` — an
  inactive source — when disabled or keyless) keeps the poll generic. A key-gated
  source that isn't configured is **skipped as inactive** (surfaced in the new
  `DiscoveryOutcome.inactive` count and by `atlas discover`), never a silent drop
  or a failure. Additional aggregators (HN "Who is hiring", arbeitnow) remain a
  fast-follow.
- **`[aggregators]` config section** (`AggregatorsConfig` / `AdzunaConfig` /
  `UsajobsConfig`): per-provider `enabled` flags, the USAJOBS `email` and Adzuna
  `country` (non-secret), and keyring **handles** for each credential (never the
  secret itself), mirroring the `[ai.backends]` shape. Ships disabled; a missing
  section still yields a valid `Config`.
- **`atlas source key <aggregator>` command** (PROJECT.md §5.4-B, §9): stores a
  key-gated aggregator's API credential(s) in the OS keychain via hidden prompts
  (never echoed, never in shell history) — the first secret-writing path in the
  CLI. Rejects an unknown or free (no-key) aggregator, and a missing keychain,
  with exit `1`. `atlas source add` now points key-gated providers at it.
- **Aggregator health in `atlas doctor`**: a second "Aggregator sources" table
  (and a `DoctorReport.aggregators` JSON field) reporting each provider as
  `active` / `needs API key` / `disabled`, so the user can see which job sources
  are usable. Aggregators are optional, so they do not affect the overall
  healthy/unhealthy exit code.
- **Aggregator adapters + saved keyword searches** (`atlas.discovery.aggregators`):
  the second discovery strategy alongside the ATS watchlist (PROJECT.md §5.4-B),
  so the daemon now finds jobs from keyword searches across many companies, not
  only per-company boards. An `AggregatorAdapter` Protocol + registry paralleling
  the ATS adapters, with two free/no-key reference implementations — **RemoteOK**
  (`https://remoteok.com/api`, a raw JSON array whose leading legal notice and
  malformed rows are skipped) and **Remotive**
  (`https://remotive.com/api/remote-jobs?search=…`, a wrapped `{jobs: […]}` API).
  Unlike an ATS adapter, an aggregator has no `detect(url)` (a source is named, not
  a pasted URL) and each posting carries its own company. A shared
  `matches_search` applies the saved search's query / location / remote filters
  uniformly after normalization. Key-gated aggregators (Adzuna, USAJOBS) are a
  documented fast-follow. Fetching goes through the existing `Fetcher` seam, so the
  adapters run offline in tests.
- **`SavedSearch` + aggregator persistence** (`atlas.discovery`): a per-profile
  saved search (query + location + remote) persisted as a `JobSource`
  (`type="aggregator"`) whose config carries the aggregator name and the serialized
  search — **no migration** (the `job_source` table already has `type` / `config` /
  `profile_id` / `enabled` / `last_polled_at`). `get_or_create_aggregator_source`
  dedups by the `(aggregator, normalized search, profile_id)` triple;
  `add_saved_search` and `persist_aggregated` (which get-or-creates a company per
  posting, since an aggregator spans many) join the discovery service; and
  `run_aggregator_poll` is the best-effort-per-source poll mirroring
  `run_discovery_poll`.
- **`atlas source add|list` commands** (PROJECT.md §9): `source add <aggregator>
  --query <q> [--location <l>] [--remote/--onsite]` validates the aggregator against
  the registry (unknown → exit `1` listing the supported providers), resolves the
  active profile (none → exit `1` with an `atlas init` hint), and saves the search
  (re-adding is a no-op); `source list` shows the saved searches (Rich table /
  `--json`).
- **Aggregator polling wired into discovery**: `atlas discover` and the daemon tick
  now run the aggregator poll **after** the ATS poll and before scoring, so
  newly-discovered aggregator postings are scored on the same pass; `discover`
  reports the combined counts.
- **Lever, Ashby, and Workday ATS adapters** (`atlas.discovery.ats`): three new
  discovery sources alongside Greenhouse (PROJECT.md §5.4-A), each a drop-in on the
  existing registry — the daemon poll, watchlist service, and `atlas company add`
  are generic over the `ats_type` string, so no downstream code changed. Each
  adapter's `detect(url)` recognizes both the public board URL and the raw API URL:
  **Lever** (`jobs.lever.co/<site>` / `api.lever.co/v0/postings/<site>`, a raw JSON
  array); **Ashby** (`jobs.ashbyhq.com/<name>` /
  `api.ashbyhq.com/posting-api/job-board/<name>`, deriving the external id from the
  job's URL since Ashby exposes none, and skipping unlisted postings); and
  **Workday** (`<tenant>.<wdN>.myworkdayjobs.com` — a POST-based, paginated CxS API,
  with a compound `<tenant>:<wd>:<site>` board reference). Known limitations: Lever
  polls the US base only, and Workday apply URLs omit any locale segment.
- **POST support on the `Fetcher` seam** (`atlas.scrape.fetcher`): the `Fetcher` /
  `BrowserFetcher` protocols and `default_fetcher` gained optional, GET-defaulted
  `method` / `json_body` / `headers` params so an ATS adapter can issue a JSON POST
  (Workday's CxS API) over the same boundary. Backward compatible — existing GET
  callers are unchanged; the test `FakeFetcher` now records these and can replay a
  sequence of pages for pagination.
- **Discover screen** (`atlas.tui.screens.discover`): the TUI's ranked queue of
  scored postings (PROJECT.md §8 screen #2) — the piece that makes the daemon's
  discovery/scoring work visible and actionable, closing Journey B (background
  discovery → review → tailor). A `DataTable` ranked by fit (score / verdict /
  company / title / location / salary / source / queue state) with the AI's
  rationale shown in a detail pane, reached with `w`. Its actions: **Enter** drills
  into Posting detail, **`t`** tailors the posting off the event loop (a thread
  worker; on success it opens the new application's detail), **`x`** dismisses a
  posting (hiding it from the queue), **`s`** saves it for later, and **`o`** opens
  its apply URL in the browser. The Posting-detail screen (§8 screen #3) also gained
  a **Tailor** action. Data comes from the pure `build_discover_queue` builder.
- **`list_scored_postings`** (`atlas.matching.repository`): the ranked query behind
  the Discover queue — each posting paired with its latest `MatchScore`, scored-only,
  dismissed excluded, ordered by fit (score descending).
- **`JobPosting.queue_status`** (`new` / `saved` / `dismissed`, a `QueueStatus`
  enum) with an Alembic migration (`server_default='new'`, so existing rows
  backfill): the posting-level triage state the Discover queue's dismiss/save
  actions set, distinct from the application-level `ApplicationStatus`.
  `set_posting_queue_status` (`atlas.scrape.repository`) is its mutator.
- **`atlas.platform.browser`**: a `UrlOpener` seam (`default_url_opener` via
  `webbrowser.open`, `UrlOpenError`) mirroring the file opener, so the Discover
  queue can launch a posting's apply URL cross-platform while the suite stays
  hermetic (a `FakeUrlOpener` is injected).
- **Company watchlist + Greenhouse ATS discovery** (`atlas.discovery`): the first
  real discovery source (PROJECT.md §5.4-A), so the daemon now *finds* jobs
  rather than only re-scoring pasted ones. An extensible `AtsAdapter` Protocol +
  registry (`atlas.discovery.ats`) with a **Greenhouse** adapter that detects a
  board token from a careers/board URL (offline, no `--ats` flag) and normalizes
  the public boards JSON API into postings; a watchlist persisted on the existing
  `company` / `job_source` tables (an ATS board is a `JobSource(type="ats")` whose
  config carries `ats_type` / `board_token` / `company_id`, so **no migration**);
  and `run_discovery_poll`, a best-effort-per-source poll that fetches each enabled
  board, deduplicates (by the source's external id, then by the normalized-apply-URL
  `dedupe_hash` shared with `atlas add`), and persists new postings. Lever/Ashby/
  Workday are fast-follow adapters that drop into the same registry.
- **`atlas company add|list` and `atlas discover` commands** (PROJECT.md §9):
  `company add <url>` auto-detects the ATS + board token from the URL and
  watchlists the company (an unrecognized URL exits `1` naming the supported
  providers; `--name` overrides the display name; re-adding is a no-op);
  `company list` shows the watchlist (Rich table / `--json`); `discover` runs one
  poll now over the watchlist and reports the outcome (`--json`), AI-free (it hints
  at `atlas score` / the daemon to score the new postings).
- **Discovery wired into the daemon poll**: `atlas daemon start` now runs a
  discovery poll over the ATS watchlist **before** the scoring poll each tick, so
  newly-discovered postings are scored on the same pass (discovery commits first;
  the scoring poll's `list_unscored_postings` picks them up).
- **Background daemon** (`atlas.daemon`): the first Phase 2 feature (PROJECT.md
  §4.1) — a long-running scheduler process. It runs one scheduled job today, the
  **scoring poll** (`run_scoring_poll`), which clears the fit-score backlog by
  scoring every not-yet-scored posting against the active profile (best-effort per
  posting, so one unscoreable posting never aborts the batch). The scheduler is
  APScheduler behind an injectable `Scheduler` seam (`register_poll_job` wires the
  job from the `[discovery]` interval; the real `BlockingScheduler` is built by a
  pragma'd factory that imports APScheduler lazily, so the hermetic suite never
  loads it). Lifecycle (`start_daemon` / `stop_daemon` / `daemon_status`) is
  tracked by a PID file under the state dir, with the OS process operations behind
  an injectable `ProcessControl` seam — everything but the real scheduler start and
  OS signals is hermetically testable. The IPC surface for the TUI, desktop
  notifications, and discovery-source polling are later Phase 2 work.
- **`atlas daemon start|stop|status` commands** (PROJECT.md §9): `start` runs the
  scheduler in the foreground (blocking; background it with your OS service
  manager) and refuses to start if one is already running; `stop` signals the
  running daemon and clears its PID file; `status` reports running/stopped (Rich
  grid or `--json`). Unknown-config / already-running / not-running cases exit `1`.
- **`[discovery]` config section** (`DiscoveryConfig`): `poll_interval_minutes`
  (default `120`, drives the daemon's poll) and `enable_scraping` (default
  `false`, reserved for the later opt-in scraping phase), per PROJECT.md §10.
  Previously ignored-by-design; now loaded into `Config.discovery`.
- **`list_unscored_postings`** (`atlas.matching.repository`): returns postings
  with no `MatchScore` yet — the fit-score backlog the daemon's poll drains.
- **`pid_file()`** (`atlas.config.paths`): the daemon's PID-file path under the
  state dir.
- New runtime dependency: `apscheduler` (the daemon's scheduler).
- **Tailor workspace TUI screen** (`atlas.tui.screens.tailor_workspace`): the
  final slice of Phase 1 item #6 (PROJECT.md §8, screen #4), which **completes the
  core loop**. Opened from the Application-detail screen (press `t`), it shows the
  master-resume blocks, the latest tailored selections (each with its reason), and
  a materials summary, and runs the four actions that produce them — **Tailor**,
  **Cover letter**, **Re-render**, **Open**. Because every Atlas service is
  synchronous and blocks (subprocess AI, network, WeasyPrint), each action runs in
  a **Textual thread worker** (`@work(thread=True)`) so the UI never freezes; the
  first worker in the codebase. Completion is handled in `on_worker_state_changed`
  (success → refresh + toast; the service's typed errors → an error toast, with
  `exit_on_error=False` so a failure never tears down the app). Interactive editing
  (include/exclude/pin) and per-section regenerate remain a follow-up (§5.7).
- **`AtlasApp` action boundaries**: the app now accepts injected
  `provider` / `renderer` / `opener` / `tailoring` / `render_config` (all optional)
  plus `run_tailor` / `run_cover_letter` / `run_rerender` / `run_open` methods that
  the workspace's workers call. An `actions_enabled` property gates the AI/render
  actions. `atlas tui` builds the provider chain + renderer **best-effort**: if they
  can't be built (e.g. no key configured) the TUI still launches **browse-only** —
  the read/track screens need no AI — and the Tailor actions are disabled with a
  hint to run `atlas doctor`.
- **Core TUI** (`atlas.tui`): the interactive Textual app (PROJECT.md §8) — the
  second slice of Phase 1 item #6, on top of the tracking core. Four screens:
  the **Dashboard** (pipeline funnel, active profile, recent activity, upcoming
  deadlines), **Applications** (a table and a Kanban board grouped by status,
  toggleable), **Application detail** (status timeline, prepared materials, fit,
  notes), and **Posting detail** (normalized fields + latest fit). Applications
  and Application detail can drive a status change through the state machine (a
  picker → `set_application_status`; illegal moves surface an error toast). All
  data logic lives in pure builders (`atlas.tui.data`) and the reused CLI
  `build_*` functions, so the screens stay a thin presentation layer exercised
  by Textual's `Pilot` harness; only the real `app.run()` is excluded from
  coverage. The action-heavy Tailor workspace and wiring tailoring/cover/score
  through background workers remain for the follow-up that completes item #6.
- **`atlas tui` command** (PROJECT.md §9): launches the interactive TUI, opening
  the Dashboard over your saved data. Console logging is quieted first (file
  logging continues) so records don't corrupt the display. Bare `atlas` still
  shows help; launching the TUI on bare invocation is a separate later decision.
- **`count_applications_by_status`** (`atlas.tracking.repository`): a status-count
  aggregate (`func.count` + `group_by`) backing the Dashboard funnel.
- New dependencies: `textual` (the TUI runtime) and `pytest-asyncio` (dev, for
  the first async `Pilot` tests); `asyncio_mode = "auto"` is set for pytest.
- **Application-tracking core** (`atlas.tracking`): the first slice of Phase 1
  item #6 (PROJECT.md §5.12) — the behavior on top of the `application` table
  that landed with tailoring, so **no migration is needed** (the schema already
  carries the full §6 column set). A pure status **state machine**
  (`ApplicationStatus` covering `saved → preparing → ready → applied → oa →
  interview → offer / rejected / withdrawn / ghosted`, with a forward-leaning
  `ALLOWED_TRANSITIONS` graph and `can_transition`); a transition service that
  records each change as a timestamped `StatusTransition` in `status_history`,
  bumps `updated_at`, stamps `applied_at` when an application first reaches
  `applied`, and records `outcome` on reaching a terminal stage; and a
  `list_applications` query (filterable by status/profile, newest-updated first).
  The clock is injected so persisted timestamps are deterministic in tests. The
  first Textual TUI screens (PROJECT.md §8) remain for a follow-up — this PR is
  the data foundation they read.
- **`atlas status set <application_id> <stage>` command** (PROJECT.md §9): moves
  an application to a pipeline stage, validating the transition against the state
  machine and recording it in the status history (with an optional `--due`
  advisory deadline). A `--force` flag overrides the machine for out-of-band
  moves. Rich detail grid or `--json`; an unknown application id or an
  illegal transition (without `--force`) exits `1`.
- **`atlas apply mark <application_id>` command** (PROJECT.md §9): a convenience
  that moves an application to `applied` and records the applied date, with the
  same `--force`/`--json` behavior. An unknown id or an illegal move exits `1`.
- **`atlas list` command** (PROJECT.md §9): lists tracked applications
  (id, status, posting title/company, latest fit, applied date), most recently
  updated first, filterable by `--status` (pipeline stage) and `--profile`. Rich
  table or `--json`.
- **Cover-letter generator** (`atlas.coverletter`): the final slice of Phase 1
  item #5 (PROJECT.md §5.8), which **completes the tailoring + rendering loop**. An
  honesty-governed AI pass (`write_cover_letter`) drafts a structured letter
  (greeting, hook, body paragraphs, close) grounded in the application's tailored
  resume selections — or, when none exists, the master resume — plus the posting,
  and renders it to a PDF matching the résumé styling via a new `matching`
  cover-letter theme. Truth-anchored (claims must trace to real material) and
  persisted as a versioned, append-only `cover_letter` row so it can be
  re-rendered without the AI. Every boundary (provider, renderer, clock, renders
  dir) is injected, so the flow is hermetic.
- **`atlas cover <job_id>` command** (PROJECT.md §9): writes a cover letter for a
  saved posting (with `--tone`) and renders it to a PDF, reporting the path, what
  it was grounded on, and any unsupported-keyword gaps (Rich detail grid or
  `--json`). Unknown posting id, no active profile, no material to ground in,
  invalid config/engine, or unusable AI output exit `1`.
- **`atlas render <application_id>` and `atlas open <application_id>` commands**
  (PROJECT.md §9): `render` re-renders an application's materials — the latest
  tailored resume and cover letter — to fresh PDFs **deterministically from their
  stored content, with no AI call**, skipping whichever material doesn't exist;
  `open` opens the exported PDFs in the OS default viewer. Both `--json`-capable;
  an unknown application id exits `1`.
- **`atlas.platform` package** with a `FileOpener` seam (PROJECT.md §12.1): an
  injectable file-open boundary (`default_file_opener` dispatches by `sys.platform`
  — `os.startfile` / `open` / `xdg-open`), so `atlas open` works cross-platform and
  the suite stays hermetic (a fake opener is injected). The first piece of the
  planned platform-abstraction layer.
- **`cover_letter` table** (`atlas.db.models`, PROJECT.md §6) with an Alembic
  migration; append-only and versioned per application, referencing the rendered
  PDF by path (never a DB blob, §6). The `matching` cover-letter theme and the
  `write_cover_letter` v1 prompt (`WRITE_COVER_LETTER_PROMPT_VERSION`) ship
  alongside it, and `get_application` / `ApplicationNotFoundError` were added to
  `atlas.tailor` for the application-keyed commands. The previously-unconsumed
  `[render] cover_theme` config is now used.
- **Resume tailoring engine** (`atlas.tailor`): the second slice of Phase 1 item
  #5 (PROJECT.md §5.7). Produces a truth-anchored, one-page tailored resume PDF
  for a stored posting: an honesty-governed AI pass (`select_and_reword`) selects
  and rewords the most relevant master-resume content — every item traceable to a
  source block by `content_id`, with hallucinated ids dropped — then a
  deterministic safety net restores month-precision dates the model may have
  dropped (§5.7 step 6), and a render-measure-trim loop packs the result onto one
  page using the `atlas.render` pipeline. The AI provider, PDF renderer, clock,
  and output directory are all injected, so the whole flow (including the trim
  loop) is exercised hermetically. Diff-mode, the separate honesty-validation /
  AI-phrase-scrub / keyword-gap passes, and per-profile honesty are deferred to a
  follow-up.
- **`atlas tailor <job_id>` command** (PROJECT.md §9): tailors your resume to a
  saved posting and renders it to a PDF, reporting the path, included-block count,
  page count, and any unsupported-keyword gaps (Rich detail grid or `--json`).
  Unknown posting id, no active profile, no master resume, invalid config/engine,
  or unusable AI output exit `1`.
- **`[tailoring]` config section** (`TailoringConfig`): `honesty_level` (a
  `strict` / `reword_only` / `light_inference` `HonestyLevel` enum, default
  `light_inference` per §11) and `enforce_one_page` (default `true`), per
  PROJECT.md §10. Previously an ignored block; now loaded into `Config.tailoring`.
- **`application` and `tailored_resume` tables** (`atlas.db.models`, PROJECT.md
  §6) with an Alembic migration. `application` ships its full §6 column set (status
  machine + Kanban/TUI arrive with application tracking, item #6, needing no
  further migration); `tailored_resume` is append-only and versioned per
  application, referencing the immutable `master_resume_version` and the rendered
  PDF by path (never a DB blob, §6).
- **`select_and_reword` v1 prompt templates** (`atlas.ai.prompts`): the third task
  in the versioned Jinja2 prompt library, with a `SELECT_AND_REWORD_PROMPT_VERSION`
  constant.
- **Rendering pipeline foundation** (`atlas.render`): the first slice of Phase 1
  item #5 (PROJECT.md §5.11). Renders the master resume to a one-page PDF through
  an HTML/CSS → PDF pipeline — a Jinja2 HTML theme (`clean-one-page`, ATS-safe,
  single-column) rendered against a view model built from the content-ID'd resume
  blocks, turned into a PDF by an injectable `PdfRenderer`. The default renderer
  uses **WeasyPrint**, imported lazily behind the seam (marked `# pragma: no
  cover`) so the hermetic suite injects a fake and never loads WeasyPrint or its
  system libs. The renderer reports the measured **page count** — the signal the
  one-page enforcement loop will consume when tailoring lands — and `atlas.render`
  warns when the resume overflows one page. Rendered PDFs are stored on disk under
  the data dir (referenced by path, never as DB blobs, §6). Other backends
  (`engine = "chromium"`) are rejected with a clear error until implemented.
- **`atlas resume render` command** (PROJECT.md §9): renders the latest
  master-resume version to a PDF and reports the path, page count, version, and
  theme (Rich detail grid, or `--json` for scripting). Rendering is deterministic
  (no AI). Invalid config, an unsupported render engine, or no master resume exit
  `1`.
- **`[render]` config section** (`RenderConfig`): `engine` (default `weasyprint`),
  `resume_theme` (default `clean-one-page`), and `cover_theme` (default `matching`,
  reserved for the later cover-letter step), per PROJECT.md §10. Previously an
  ignored block; now loaded into `Config.render`.
- New runtime dependency: `weasyprint` (the pure-Python HTML/CSS → PDF renderer).
- **Fit scoring** (`atlas.matching`): the fourth Phase 1 feature (PROJECT.md
  §5.6, §7 `score_fit`). Scores a stored `JobPosting` against the active
  profile's preferences and a compact master-resume summary: it asks the AI (via
  `complete_json` through the versioned `score_fit` Jinja2 prompt) for a
  structured `FitAssessment` (score 0-100, verdict, rationale, matched strengths,
  gaps, dealbreaker hits, salary fit) and computes deterministic signals
  (salary / location / work-auth / deal-breakers) locally that are passed into
  the prompt as context and shown as badges — they inform and annotate the score
  but never pre-discard a posting (§5.6). Unlike the scrape parser, a failed
  scoring call surfaces as an error (a bogus score would pollute the queue)
  rather than degrading to a placeholder. Every external boundary (provider,
  clock, session) is injected so the suite stays hermetic.
- **`atlas score <id>` command + `atlas add` scoring integration** (PROJECT.md
  §9): `score` scores a saved posting for fit and prints the assessment (Rich
  detail grid with signal badges, or `--json` for scripting); re-scoring appends
  a new assessment rather than replacing the last. `atlas add` now scores a
  newly-saved posting in its own transaction (best-effort — a missing
  profile/resume or AI failure prints a hint and keeps the saved posting rather
  than failing). `atlas postings list`/`show` surface each posting's latest
  fit score and verdict. Unknown ids, no active profile, no master resume, and
  unusable AI output exit `1`.
- **`match_score` table** (`atlas.db.models`, PROJECT.md §6) with an Alembic
  migration. Beyond the §6 column list (score, verdict, rationale,
  matched_strengths / gaps / dealbreaker_hits JSON, model, created_at) the row
  also persists `salary_fit` and a `signals` JSON blob, so the deterministic
  badges render on re-view without recomputing against a since-changed profile.
  Scores are **append-only** (mirroring the immutable master-resume versioning),
  preserving the history of how a posting's fit changed.
- **`score_fit` v1 prompt templates** (`atlas.ai.prompts`, PROJECT.md §7): the
  second task in the versioned Jinja2 prompt library, with a
  `SCORE_FIT_PROMPT_VERSION` constant.
- **Paste-URL scrape & parse** (`atlas.scrape`): the third Phase 1 feature
  (PROJECT.md §5.5). Turns a job-posting URL into a normalized, persisted
  `JobPosting`. Fetching is synchronous behind an injectable `Fetcher` protocol
  (an `httpx`-backed default; a `BrowserFetcher` seam reserves the future
  Playwright JS-render fallback, not wired yet). Extraction prefers structured
  data — JSON-LD schema.org `JobPosting`, then OpenGraph — and falls back to the
  page's main text; a structured posting with a title short-circuits the AI,
  otherwise the **`parse_job_posting` AI extraction pass** runs (the first
  command-flow model call in Atlas). Per §7, an `LLMOutputError` degrades
  gracefully: the raw page text is kept as the description so a difficult page is
  still saved. Postings are deduplicated by normalized apply URL (re-adding a URL
  is a no-op), the raw HTML is stored on disk as a snapshot (referenced, never a
  DB blob), and every external boundary is injected so the suite stays hermetic.
- **`atlas add <url>` + `atlas postings list|show` commands** (PROJECT.md §9):
  `add` scrapes, parses, and saves a posting (reporting the saved posting or a
  no-op); `postings list`/`show` render saved postings (Rich table / detail grid,
  `--json` for scripting). Fetch/extraction failures and unknown ids exit `1`.
- **`company`, `job_source`, `job_posting` tables** (`atlas.db.models`, PROJECT.md
  §6) with an Alembic migration. The paste-URL flow dedupes companies by name and
  reuses one `type="url"` job source (§5.4); the tables are reused as-is by the
  Phase 2 discovery daemon.
- **Versioned Jinja2 AI-prompt library** (`atlas.ai.prompts`, PROJECT.md §7,
  §18.1): `render_prompt(task, version, **context)` loads a task's
  `system.jinja` + `user.jinja` from `templates/<task>/v<version>/` through a
  `StrictUndefined` environment (a missing context variable fails loudly),
  returning a `RenderedPrompt` that records the task and version used. Ships the
  `parse_job_posting` v1 templates. Replaces the inline-constant prompt idiom.
- New runtime dependencies: `httpx` (fetching), `beautifulsoup4` (JSON-LD /
  OpenGraph / main-text extraction), and `jinja2` (the prompt template library).
- **Master resume ingest, parse & versioning** (`atlas.resume`): the second Phase
  1 feature (PROJECT.md §5.3). A deterministic Markdown parser splits the single
  master resume into ordered, typed blocks (contact/summary/experience/project/
  skill/education/…) by heading convention; each block gets a **stable content
  id** derived from its type and normalized text, so an unchanged bullet keeps its
  id across versions — the traceability anchor the later fit-scoring, tailoring,
  and honesty-validation steps build on. Duplicate identical blocks disambiguate
  via an occurrence index, and heading-less input is still captured best-effort.
  The AI-assisted structure extractor (the `parse_master_resume` task, §7) is not
  wired yet; `parse_markdown` exposes a `StructureExtractor` seam it will fill
  later, with no change to the deterministic path. A repository (pure functions
  over an open `Session`) and an ingest/reparse service persist **immutable,
  monotonically-versioned** rows into the new `master_resume` + `resume_block`
  tables: `atlas resume set` creates a new version only when the content changed
  (identical content is a no-op), `atlas resume reparse` re-versions from the
  stored source, and both keep earlier versions untouched.
- **`atlas resume set|reparse|show` commands** (PROJECT.md §9): `set <path>`
  ingests a Markdown resume (reporting the new version or a no-op), `reparse`
  re-versions the current resume, and `show` lists versions (Rich table or
  `--json`) marking the latest. Missing files and a not-yet-set resume map to a
  clear message and exit code 1. Logic lives in `atlas.cli.resume` (mirroring
  `atlas.cli.profile`), testable without invoking the CLI.
- **`master_resume` and `resume_block` tables** (`atlas.db.models`, PROJECT.md §6)
  with an Alembic migration: `master_resume` holds immutable per-user versions
  (version, source path, raw Markdown, parsed-structure JSON, created-at) and
  `resume_block` holds the content-ID'd blocks referencing it.
- **`UtcDateTime` column type** (`atlas.db.types`): SQLite drops `tzinfo` on a
  datetime round-trip, so this type decorator stores UTC and re-attaches it on
  load, guaranteeing timezone-aware UTC timestamps regardless of backend. Used by
  `master_resume.created_at` and by every future timestamp column.
- **Onboarding & profiles** (`atlas.profiles`): the first Phase 1 feature
  (PROJECT.md §5.2). A typed `ProfilePreferences` model captures per-profile
  job-search preferences — target roles/variants, seniority, specializations,
  location/remote posture, compensation, work authorization, company
  preferences, and deal-breakers — with `StrEnum`s for the closed domains,
  serialized into the existing `profile.preferences` JSON column (no schema
  change). A repository layer (pure functions over an open `Session`) persists
  the single user and search profiles, enforcing the single-user and
  single-active-profile invariants in code. An onboarding wizard drives the Q&A
  through an injectable `Prompter` boundary (a scripted fake replaces it in the
  hermetic suite), parsing lists/integers/enum tokens with re-prompting and
  pre-filling defaults from existing answers so the same flow powers first-run
  and edits.
- **`atlas init` + `atlas profile list|add|edit|use` commands**: `init` runs
  first-time onboarding (user + first active profile); `profile` manages
  additional profiles and switches the active one. Human-readable Rich output
  through the shared console; `--json` on `profile list` for scripting. Missing
  profile ids fail with a clear message and exit code 1.
- **Database bootstrap** (`atlas.db.initialize_database`): migrates the database
  to head and returns a ready engine (building the engine first so a fresh
  install's data dir is created before Alembic runs, disposing it on migration
  failure). The first production caller of `upgrade_to_head`, used by the
  first-run commands so a fresh install migrates on demand.
- **Logging** (`atlas.logging`): the last Phase 0 foundation — Phase 0 is now
  complete. `setup_logging` configures the `"atlas"` package logger with a Rich
  console handler on the shared **stderr** console (so records never contaminate
  stdout / `--json`) and a rotating file handler under the platformdirs state
  dir capturing `DEBUG`+. A pure `resolve_level` sets the console level by
  precedence — `--log-level` > `-v`/`-vv` > `ATLAS_LOG_LEVEL` > `[logging]`
  config > `WARNING` — skipping malformed values rather than crashing; setup is
  idempotent and its real-handler construction is an injectable seam kept out of
  the hermetic suite (AGENTS.md §6.2).
- **`[logging]` config section** (`LoggingConfig`): `level`, `file_enabled`,
  `max_bytes`, `backup_count`, defaulted and forward-compatible like `[ai]`.
- **Global `--verbose`/`-v` and `--log-level` CLI options**: the Typer top-level
  callback now initializes logging before every subcommand (a bad config file is
  tolerated so the command still reports the real error).
- **First log sites**: the previously-silent corrupt probe-cache handler
  (`ai/probe_cache`), the migration-failure path (`db/migrate`), and the API
  error classifier (`ai/api/provider`) now log — the last logging only the
  backend and exception type, never vendor diagnostics/paths/keys.
- **Data layer** (`atlas.db`): the Phase 0 SQLite foundation the Phase 1 core
  loop builds on (PROJECT.md §6, §4.1). `create_db_engine` builds a SQLite engine
  and applies `PRAGMA journal_mode=WAL` + `foreign_keys=ON` on every connection
  (WAL supports the daemon-writer / TUI-reader concurrency model); the database
  URL is an injectable boundary defaulting to `db_path()` under the platformdirs
  data dir, so the hermetic suite uses in-memory SQLite and never touches a real
  data dir (AGENTS.md §6.2). `session_scope(engine)` is a transactional context
  manager (commit on clean exit, roll back and re-raise on error, always close).
  The foundational table slice — `User` and `Profile` — ships as SQLModel tables
  with JSON-shaped columns; the remaining PROJECT.md §6 tables land per-feature in
  Phase 1, each with its own migration.
- **Alembic migrations**: an in-process driver (`atlas.db.migrate` —
  `alembic_config(url)` / `upgrade_to_head(url)`, failures normalized to
  `MigrationError`) so Atlas migrates on launch without shelling out, plus the
  migration environment (targets `SQLModel.metadata`) and the initial-schema
  migration creating `user` and `profile`. The migration is proven end-to-end by
  a test that runs `upgrade head` against a temporary database; `alembic.ini` is
  the developer-CLI entry. `DatabaseError` base + `MigrationError` error types.
- New runtime dependencies: `sqlmodel` (Pydantic + SQLAlchemy table models) and
  `alembic` (schema migrations).
- **Minimum Claude Code CLI version enforcement**: `CliAdapter` gained a
  `parse_cli_version` helper, an overridable `_minimum_version()` hook, and a
  `check_availability()` returning a `CliAvailability(available, reason)`. The
  Claude Code adapter requires ≥ 2.1.205 (the release exposing the stream-json
  structured error category); an older CLI is reported unavailable with a
  version-specific reason in `atlas doctor` (failover to OpenRouter still
  applies). Resolves the CLI version-minimum open question (PROJECT.md §18.2).
- **AI backend capability probe** (`atlas.ai.probe`): `probe_backend(provider)`
  runs a tiny "reply OK as JSON against this schema" round-trip and reports a
  `BackendCapabilities` across the five capabilities the design names — JSON
  output, JSON schema, streaming, system-prompt injection, and model override
  (the first two deterministic, the last three best-effort). Pure logic over the
  `LLMProvider` protocol, so the default suite drives it with a fake provider and
  no live call.
- **Probe-result cache** (`atlas.ai.probe_cache`): persists `ProbeResult`s (keyed
  by backend name) as JSON under the platformdirs cache dir; a missing or corrupt
  cache is treated as empty rather than raising.
- **`atlas doctor --probe` / `--refresh`**: `atlas doctor` now reports each
  backend's capabilities. By default it makes no model call and shows cached
  capabilities; `--probe` runs the live (billable) round-trip, reusing cached
  results and persisting fresh ones; `--refresh` re-probes every backend.
  Capabilities appear as a themed column (and in `--json`).
- **Styled, consistent CLI output** via Rich: a shared console + named theme
  (`atlas.cli.console`, `ATLAS_THEME`) that every command renders through, using
  semantic style names (`success`/`error`/`heading`/`accent`/…) so the palette is
  centralized and all commands match. Errors route to a stderr console;
  machine-readable `--json` output stays unstyled and pipe-safe via
  `print_json_line`. `atlas doctor` now renders a Rich table of backends with a
  status summary. The convention (all CLI output is Rich-styled and consistent)
  is documented in `AGENTS.md` §10, `docs/agent/coding-standards.md`, and
  PROJECT.md §9/§13. Rich promoted to a direct dependency.
- Atlas **command-line interface** (`atlas.cli`, built on Typer): a command group
  exposed via the `atlas` console script and `python -m atlas`, with a top-level
  callback keeping it in multi-command mode for future subcommands.
- **`atlas doctor`** command: validates configuration and reports each configured
  AI backend's availability (default + failover, in chain order). Prints
  human-readable text or `--json` for scripting; exits `0` when at least one
  backend is usable and `1` when none is (or config/keyring can't be loaded).
  Per-backend construction errors (unknown name, missing bare-mode key) are
  reported rather than aborting the report. The live "reply OK as JSON"
  capability round-trip is deferred to a later phase. Pure report logic lives in
  `atlas.cli.doctor` (`run_doctor`/`render_report`), testable without invoking
  the CLI.
- `build_named_provider` in `atlas.ai.router` (promoted from the private
  `_build_named`): construct a single AI backend by name, used by both
  `build_provider_chain` and `atlas doctor`.
- New runtime dependency: `typer`.
- `atlas.ai.router`: the AI backend **failover chain**. `FailoverProvider` wraps
  an ordered list of `LLMProvider` backends and is itself an `LLMProvider`, so
  callers stay agnostic; `complete()`/`stream()` try each backend in order and
  fail over on availability-signal errors (`LLMBackendError` — covering
  `LLMAuthError`/`LLMRateLimitError` — and `LLMTimeoutError`), re-raising the
  last error when all fail. `LLMOutputError` is deliberately not a trigger: it is
  a content/schema failure surfaced after `complete_json()`'s recovery ladder, so
  it propagates and stops the walk. `build_provider_chain(config, store)`
  assembles the chain from `AiConfig` (`default_backend` then each `failover`
  name — `claude_code` → `openrouter`), raising a clear error for an unknown
  backend name.
- `build_claude_code_provider`: a config-driven factory for the Claude Code CLI
  backend (mirroring `build_openrouter_provider`), resolving the `--bare`-mode
  `ANTHROPIC_API_KEY` via `resolve_api_key` (keyring first, env fallback) only
  when `use_bare` is set and passing it directly, never via `os.environ`.
- `ClaudeCodeBackend.api_key_handle` (default `"anthropic"`): the keyring handle
  for the bare-mode key, mirroring `OpenRouterBackend.api_key_handle`.
- `atlas.ai.api` package: a single `LiteLLMProvider` implementing `LLMProvider`
  for every hosted-model backend (OpenRouter, Bedrock, Anthropic, Gemini, …), so
  adding a vendor is configuration rather than code, plus
  `build_openrouter_provider` — Atlas's default API failover backend. LiteLLM
  sits behind two injectable seams so its heavy import never happens in the
  hermetic test suite and the API path stays swappable: `CompletionFn`
  (`client.py`), the `litellm.completion` call boundary owning the transport
  retry layer (`num_retries`) with `drop_params`; and `CapabilityFn`
  (`capabilities.py`), a per-model schema-support lookup from LiteLLM's registry
  (not hardcoded), so `response_format` is requested only where supported and
  `complete_json()` recovers structure from text elsewhere. The provider applies
  a per-provider adaptive timeout, maps `ModelResponse` onto
  `LLMResponse`/`Usage` (tokens + cost) via defensive access without importing
  LiteLLM's types, and classifies failures by HTTP status/message into
  `LLMAuthError`/`LLMRateLimitError`/`LLMTimeoutError`/`LLMBackendError`. The
  OpenRouter factory resolves the key via `resolve_api_key` (keyring first,
  `OPENROUTER_API_KEY` fallback) and passes it to LiteLLM directly, never via
  `os.environ`. Reusable offline `FakeChatCompleter`/`FakeModelResponse` test
  doubles added to `tests/conftest.py`.
- New runtime dependency: `litellm` (the API-backend layer, kept behind Atlas's
  `LLMProvider` interface).
- `atlas.config` package: cross-platform paths via `platformdirs`
  (`config_dir`/`data_dir`/`cache_dir`/`state_dir`/`config_file`); a lean,
  forward-compatible TOML config schema (`Config`/`AiConfig`/backends, unknown
  keys ignored) with `load_config`/`save_config` (stdlib `tomllib` read,
  `tomli_w` write); and keyring-backed secrets — `SecretStore` + a single
  `resolve_api_key()` path (keyring first, optional env-var fallback that local
  providers can disable, keys never written to `os.environ`). Backend selection
  refuses insecure plaintext storage: a real OS keychain is preferred and a
  headless box uses the `keyrings.alt` encrypted-file backend only when
  `ATLAS_KEYRING_PASSWORD` is set, else raises `KeyringUnavailableError`.
- `ClaudeCodeAdapter` (`src/atlas/ai/cli/claude_code.py`): Atlas's default
  coding-CLI backend. Drives `claude -p … --output-format json --json-schema …`
  (neutralized: `--append-system-prompt` "do not use tools", no `--allowedTools`,
  scratch cwd), maps the envelope onto `LLMResponse`, supports `--bare` +
  injected `ANTHROPIC_API_KEY`, and classifies failures as
  `LLMAuthError`/`LLMRateLimitError`/`LLMBackendError`.
- `LLMAuthError` and `LLMRateLimitError` (subclasses of `LLMBackendError`) in the
  AI error hierarchy (`src/atlas/ai/base.py`).
- `CliAdapter` env and error-classification hooks (`_env_for`, `_classify_error`)
  so subclasses can inject secrets and distinguish failures.
- `atlas.ai.cli` subprocess boundary: a frozen `RunResult`, the runtime-checkable
  `SubprocessRunner` protocol, and `default_subprocess_runner` (starts the child
  in its own process group and kills the tree on timeout) —
  `src/atlas/ai/cli/runner.py`.
- `CliAdapter` base class (`src/atlas/ai/cli/base.py`): the reusable machinery
  every coding-CLI backend subclasses — per-call scratch cwd, request-timeout
  enforcement, `is_available()` version probe, error normalization, and a
  single-chunk `stream()` fallback; subclasses supply `_build_argv` and
  `_parse_response`.
- `LLMTimeoutError` and `LLMBackendError` in the AI error hierarchy
  (`src/atlas/ai/base.py`).
- `atlas.ai` core contract: the `LLMProvider` protocol and `LLMRequest`,
  `LLMResponse`, and `Usage` models, plus the `LLMError` / `LLMOutputError`
  hierarchy (`src/atlas/ai/base.py`).
- `complete_json()`: the provider-agnostic structured-output recovery ladder
  (native structured field → balanced-JSON extraction → bounded content retries
  with temperature escalation → prompt-only fallback → `LLMOutputError`),
  generic over the target Pydantic model (`src/atlas/ai/complete_json.py`).
- First runtime dependency: `pydantic`.
- uv-managed project scaffold: `pyproject.toml` (hatchling build, version sourced
  from `atlas.__version__`), committed `uv.lock`, `src/atlas` package with a
  `py.typed` marker, and smoke tests.
- Tooling configuration for `ruff` (format + lint), `mypy --strict`, and `pytest`
  with a 100% line/branch coverage gate.
- GitHub Actions CI running the full quality suite on the Windows/macOS/Linux
  matrix (Python 3.11–3.13) via uv.
- `.pre-commit-config.yaml` mirroring the CI gates for fast local checks.
- GitHub repository metadata: pull request template (Definition of Done),
  bug/feature issue templates, Dependabot (uv + GitHub Actions), and CODEOWNERS.
- `CHANGELOG.md` and `CONTRIBUTING.md`.
- `docs/STATUS.md` session pick-up doc (current phase, what's landed, next step),
  wired into `AGENTS.md` as the mandatory first read and into the Definition of
  Done so it stays current.

### Changed

- **`atlas add` now scores a newly-saved posting** (previously scoring was a
  separate step). Scoring runs in its own transaction after the posting is
  committed, so a scoring failure (e.g. no profile/resume yet) prints a hint and
  never discards the saved posting.
- **Claude Code adapter now drives `--output-format stream-json --verbose`**
  instead of `--output-format json`. The terminal `result` event still carries
  `structured_output`/`result`/`usage`/`total_cost_usd` (verified against the
  real CLI), so the structured-output contract is unchanged — but failures now
  carry a **structured `error` category** (`authentication_failed`, `rate_limit`,
  …), so `_classify_error` maps auth/rate-limit failures from that category
  rather than string-matching stderr (the stderr heuristic remains a fallback).

[Unreleased]: https://github.com/Harikeshav-R/Atlas/commits/main
