# Atlas — Project Status (start here)

> **New session? Read this file first, then [`AGENTS.md`](../AGENTS.md).** This is the
> single "you are here / do this next" pointer. It tells a fresh coding-agent (or human)
> session where the project stands and what to pick up, without reverse-engineering it
> from git history.
>
> **Keep it current.** Updating this file is part of the [Definition of Done](../AGENTS.md#8-definition-of-done):
> whenever a roadmap item lands, tick it here and move the "Next up" pointer. A stale
> STATUS.md is a bug.

- **Last updated:** 2026-08-05 (**the TUI Discover queue landed** — `DiscoverScreen`
  ranks scored postings by fit with tailor / dismiss / save / open-URL actions and
  drill-in, backed by `list_scored_postings`, a new `JobPosting.queue_status`
  (migration), and a `UrlOpener` seam. Journey B — background discovery → review →
  tailor — is now closed end-to-end. Earlier the same phase: the daemon + scheduler
  and the company watchlist + Greenhouse ATS discovery. **Next:** Lever/Ashby/Workday
  adapters, aggregators, multiple profiles, and the daemon IPC surface)
- **Current phase:** Phase 2 — Discovery & background 🚧 (daemon + scheduler ✅;
  company watchlist + Greenhouse ATS discovery ✅; **scored Discover queue in the
  TUI ✅** — `DiscoverScreen` + `list_scored_postings` + `queue_status` +
  `UrlOpener`; **more ATS adapters, aggregators, multiple profiles, IPC next**).
  Phase 1 core loop ✅ complete.
- **Design source of truth:** [`docs/PROJECT.md`](./PROJECT.md) — especially the
  [phased roadmap](./PROJECT.md#15-phased-roadmap).
- **Working agreement:** [`AGENTS.md`](../AGENTS.md) (branching, commits, tests, PR flow).

---

## ▶ Next up (do this next)

**Phase 2 (Discovery & background) is well underway.** The **daemon + scheduler**, the
**company watchlist + Greenhouse ATS discovery**, and now the **scored Discover queue in the
TUI** have landed (see "What has landed"). The daemon discovers postings from watchlisted ATS
boards and scores them; `DiscoverScreen` (press `w`) presents them ranked by fit with tailor /
dismiss / save / open-URL actions — so Journey B (background discovery → review → tailor) works
end-to-end.

**Do these next to grow discovery (PROJECT.md §4.1, §5.4, §15):**
1. **More ATS adapters** — **Lever**, **Ashby**, **Workday**. Each is a new module in
   `atlas.discovery.ats` implementing the `AtsAdapter` Protocol (a `detect(url)` hook + a
   `list_postings` that fetches the board's public API through the injected `Fetcher`) plus one
   entry in the `_ADAPTERS` registry tuple — no interface change. Greenhouse
   (`ats/greenhouse.py`) is the worked example.
2. **Aggregator adapters** + saved keyword searches — the second discovery strategy (RemoteOK,
   Remotive, Adzuna, …), key-gated ones inactive until a key is pasted. A new
   `atlas.discovery.aggregators` package alongside `ats/`, feeding the same `persist_discovered`.
3. **Multiple profiles** fully wired (the Discover queue and scoring are single-active-profile
   today). Add the "owned by" claim convention (PROJECT.md §4.1) and a `busy_timeout` PRAGMA now
   that the daemon writes discovery rows while the TUI reads.
4. **IPC surface** — a local socket (Unix domain / Windows named pipe) so the TUI can trigger
   "poll/tailor now" and stream progress. Follow the `platform/opener.py` seam (a Protocol +
   `sys.platform`-dispatched, pragma'd transport); a pure `handle_request` is the tested core.
5. **Desktop notifications** (`desktop-notifier`, §5.16) for new high-fit matches / deadlines.

> **Deferred Phase-1 depth (optional, revisit as needed — not blockers for Phase 2):**
> **PR 2b — tailoring depth**: `honesty_validate` traceability (§11), AI-phrase scrub (§5.7
> step 5), keyword-gap suggestions (§5.7 step 4), diff-mode (§5.7), and the TUI's interactive
> editing loop — include/exclude/pin + per-section regenerate + the Questions tab (§5.7, §5.8).
> Still-unconsumed config: `AiConfig.scoring_model_tier` / `daily_spend_cap_usd` (§5.6 cost
> controls) and the per-profile honesty override (§11). The Phase-1 core loop works without
> these; they raise its quality and are picked up when Phase 2 stabilizes or on demand.

The Phase-0 AI-provider checklist below is retained as historical reference.

1. ✅ `LLMProvider` protocol + `LLMRequest`/`LLMResponse`/`Usage` models (`src/atlas/ai/base.py`)
   and the `complete_json()` structured-output ladder (`src/atlas/ai/complete_json.py`).
2. ✅ **`CliAdapter` base class** + injected `SubprocessRunner` boundary — `src/atlas/ai/cli/`.
3. ✅ **Claude Code** adapter (`src/atlas/ai/cli/claude_code.py`) — `-p`
   `--output-format stream-json --verbose --json-schema`, `--append-system-prompt` + no
   `--allowedTools`, `--bare`/`ANTHROPIC_API_KEY` opt-in (key injected, never logged), terminal
   `result` event→`LLMResponse` mapping, auth/rate-limit detection from the stream-json
   structured `error` category (stderr heuristic fallback).
4. ✅ **OpenRouter** adapter (default API failover backend) via LiteLLM behind `LLMProvider`
   (`src/atlas/ai/api/`) — consumes `resolve_api_key()` (handle `"openrouter"`) from
   `atlas.config`; two injectable seams keep `litellm` out of the hermetic suite.
5. ✅ **Failover chain** (`src/atlas/ai/router.py`) — `FailoverProvider` walks the configured
   backend chain (`claude_code` → `openrouter`) on `LLMBackendError`/`LLMTimeoutError` (not
   `LLMOutputError`); `build_provider_chain()` assembles it from `AiConfig`. A config-driven
   `build_claude_code_provider` (+ `ClaudeCodeBackend.api_key_handle`) now matches
   `build_openrouter_provider`.
6. ✅ **CLI scaffold + `atlas doctor` v1** (`src/atlas/cli/`) — a Typer command group
   (`atlas` console script + `python -m atlas`) whose `doctor` command reports each configured
   backend's availability (text or `--json`; exit 0/1). Pure report logic in `atlas.cli.doctor`.
7. ✅ **Capability probe** (`atlas.ai.probe` + `atlas.ai.probe_cache`) — a round-trip
   "reply OK as JSON against this schema" probe recording all five capabilities (JSON output /
   schema / streaming / system-prompt / model-override; last three best-effort), cached as
   JSON under the platformdirs cache dir, surfaced through `atlas doctor --probe`/`--refresh`.
8. ✅ **Structured error classification + CLI version floor** — the two previously-deferred
   riders: Claude failures classified from the stream-json structured `error` category (item 3);
   and a minimum CLI version (`CliAdapter._minimum_version` / `check_availability`), Claude Code
   pinned to ≥ 2.1.205, surfaced in `atlas doctor` (resolves §18.2).
9. ✅ Tests: fake provider + recorded fixtures, no live CLI/API calls (AGENTS.md §6.2).

> **The AI provider abstraction is now fully complete for Phase 0** — no deferred riders remain.
> (Codex/Antigravity adapters and Phase 1+ cross-cutting features — prompt library, response
> caching, TUI cost accounting, PII redaction — are out of Phase 0 scope by design.)
>
> **Phase 0 is complete:** config/keyring, the AI provider abstraction, the data layer, and
> logging have all landed — see [PROJECT.md §15](./PROJECT.md#15-phased-roadmap). **Phase 1 is
> now in progress** (onboarding + profiles landed; see "Next up" for what's next).

---

## ✅ What has landed

Phase 2 · Scored Discover queue — `atlas.tui.screens.discover` (PROJECT.md §8 screen #2 —
makes the discovery/scoring pipeline visible + actionable, closing Journey B):

- `DiscoverScreen` (press `w`): a `DataTable` ranked by fit (score / verdict / company / title /
  location / salary / source / queue state) with the AI's rationale in a detail pane, over the
  pure `atlas.tui.data.build_discover_queue` builder. Actions: **Enter** → Posting detail, **`t`**
  → tailor off the event loop (the `tailor_workspace` thread-worker pattern; on success it pushes
  the new application's detail), **`x`** → dismiss (hide from the queue), **`s`** → save, **`o`**
  → open the apply URL in the browser. Browse-only disables tailor; a worker error is toasted
  without tearing down the app. The Posting-detail screen (§8 screen #3) also gained a **Tailor**
  action.
- `atlas.matching.repository.list_scored_postings`: the ranked query — each posting with its
  latest `MatchScore` (max-id per posting, matching `get_latest_match_score`), scored-only,
  dismissed excluded, ordered by score desc then newest first (a correlated subquery, no N+1).
- `JobPosting.queue_status` (`new`/`saved`/`dismissed`, a `QueueStatus` enum) with an Alembic
  migration (`server_default='new'` backfills existing rows); `set_posting_queue_status`
  (`atlas.scrape.repository`) is the dismiss/save mutator. Distinct from the application-level
  `ApplicationStatus`.
- `atlas.platform.browser`: a `UrlOpener` seam (`default_url_opener` via `webbrowser.open`,
  `UrlOpenError`) mirroring the file opener, so the queue opens a posting's apply URL
  cross-platform; a `FakeUrlOpener` keeps the suite hermetic. `AtlasApp` gained the `w` binding,
  `action_discover`, an injected `url_opener`, and `set_queue_status` / `run_open_url`.
- 895 tests at 100% line+branch; `mypy --strict` incl. win32; no new dependency (`webbrowser`
  is stdlib). Pilot tests drive every screen path.

Phase 2 · Company watchlist + Greenhouse ATS discovery — `atlas.discovery` + `atlas company`
+ `atlas discover` (the first real discovery source — the daemon now *finds* jobs):

- `atlas.discovery.ats`: an extensible `AtsAdapter` Protocol (`ats/base.py`) with a pure,
  offline `detect(url)` hook + a `list_postings(board_ref, *, fetcher, timeout_s)` that fetches
  through the reused `scrape.fetcher.Fetcher` (no new network boundary), and a **registry**
  (`ats/__init__.py`): `get_adapter(ats_type)` (→ `UnknownAtsError`), `detect_ats(url)` →
  `(ats_type, board_token)`, and `ATS_TYPES`. The **Greenhouse** adapter (`ats/greenhouse.py`)
  detects the board token from the `boards`/`job-boards`/`embed`/subdomain URL forms and
  normalizes the public boards JSON API (`content=true`), unescaping the HTML description via the
  reused `extract_main_text` and skipping malformed jobs best-effort. `DiscoveredPosting`
  (`structure.py`) reuses `ScrapedPosting` by composition, adding only `external_id`.
- `atlas.discovery.repository`: an ATS board is a `JobSource(type="ats")` whose `config` JSON
  carries `ats_type` / `board_token` / `company_id` — **no new column, no migration** (every
  column pre-exists in the `company`/`job_source` migration). `get_ats_source` /
  `get_or_create_ats_source` dedup by `(ats_type, board_token)`; `list_enabled_ats_sources` feeds
  the poll (excludes disabled + the shared `url` source); `stamp_last_polled_at`;
  `get_posting_by_source_external` is the stable per-source re-poll key.
- `atlas.discovery.service`: `add_watchlist_company` (get-or-create the `Company` recording its
  `ats_type`/`ats_board_ref`/`domain` + the ATS source, idempotent) and `persist_discovered`
  (insert new postings, de-duplicating first by `(source, external_id)` then by the
  normalized-apply-URL `dedupe_hash` shared with `atlas add`, reusing `create_job_posting`).
- `atlas.discovery.poller`: `run_discovery_poll(session, *, fetcher, clock)` → `DiscoveryOutcome`
  (`sources_polled` / `discovered` / `skipped` / `failed_sources`), best-effort per source (an
  unknown provider, unusable board, or fetch failure is counted + skipped, never fatal), mirroring
  `run_scoring_poll`. Pure over the session → tested with `db_engine` + `FakeFetcher`.
- CLI (`atlas.cli.discovery` + `main`): `atlas company add <url>` (auto-detects ATS + token from
  the URL, `--name` override, unrecognized URL → exit 1 naming supported providers, re-add no-op),
  `atlas company list` (Rich table / `--json`), and `atlas discover` (run one poll now, AI-free,
  `--json`). The daemon's `run()` now runs discovery **before** scoring each tick, so newly-found
  postings are scored on the same pass. 100% line+branch; `mypy --strict` incl. win32; no new
  dependency. **Remaining Phase-2 discovery:** the Lever/Ashby/Workday adapters (drop into the same
  registry), aggregators, the TUI Discover queue, and the daemon IPC surface.

Phase 2 · Daemon skeleton + scheduler — `atlas.daemon` + `atlas daemon start|stop|status`
(the first Phase 2 feature — the background scheduler):

- `atlas.daemon.poll`: `run_scoring_poll(session, *, provider, clock=utcnow)` — the pure
  scheduled job. It scores every posting with no `MatchScore` yet (via the new
  `matching.repository.list_unscored_postings`) against the active profile, **best-effort per
  posting** (a `MatchingError` — no active profile / no master resume / AI failure — is counted
  and skipped, not fatal), returning a `PollOutcome` (scored / skipped). Pure over the session →
  tested directly with `FakeLLMProvider`.
- `atlas.daemon.scheduler`: a `Scheduler` Protocol (the injectable seam) + the pure
  `register_poll_job` (wires the poll on an `interval` trigger from
  `config.discovery.poll_interval_minutes`, clamped ≥ 1) + `default_scheduler` — a
  `# pragma: no cover` factory that **lazily** imports APScheduler and returns a
  `BlockingScheduler`, so the hermetic suite never imports the scheduler stack.
- `atlas.daemon.service`: the lifecycle — `start_daemon` (refuse-if-running → write PID →
  register job → `scheduler.start()`), `stop_daemon` (signal + clear PID), `daemon_status`
  (running/stopped, stale-PID-aware), and `read_pid`/`write_pid`. The OS process ops
  (`current_pid`/`is_running`/`terminate`) sit behind an injectable `ProcessControl` seam whose
  real `os.kill`-based impl is pragma'd; tests use a `FakeProcessControl`.
- Config/paths: `DiscoveryConfig` (`[discovery]` — `poll_interval_minutes`, `enable_scraping`;
  previously ignored-by-design) + `pid_file()` under the state dir.
- CLI (`atlas.cli.daemon` + `main`): `atlas daemon start` (blocking; refuses if already
  running), `stop`, `status` (Rich grid / `--json`). New `apscheduler` dep (+ mypy override, no
  stubs). 100% line+branch; `mypy --strict` incl. win32. Verified end-to-end against a temp DB:
  a poll tick scores the backlog, `status` reflects a live vs. stale PID, and `stop` clears a
  stale pidfile. The daemon's IPC surface + discovery-source polling are next.

Phase 1 · Tailor workspace + action workers — `atlas.tui` (item #6, PR 3 — **completes item #6
and the Phase 1 core loop**):

- `TailorWorkspaceScreen` (`atlas.tui.screens.tailor_workspace`): opened from Application detail
  (`t`), it shows the master-resume blocks, the latest tailored selections (content_id · included
  · reason · text), and a materials summary, and runs four actions — **Tailor** (`t`), **Cover
  letter** (`c`), **Re-render** (`r`), **Open** (`o`). Its data comes from the pure
  `build_tailor_workspace` builder (`atlas.tui.data`), reusing the resume/tailor/coverletter
  getters; the panes are read-only (interactive editing is the deferred PR-2b).
- **The first thread workers in the codebase**: each action is
  `@work(thread=True, exclusive=True, exit_on_error=False)` so the blocking service (subprocess
  AI, network, WeasyPrint) runs off the event loop and the UI never freezes (PROJECT.md §8).
  `on_worker_state_changed` handles completion — success refreshes the view + toasts; the
  service's typed errors (`TailoringError`/`CoverLetterError`/`RenderError`/`FileOpenError`/…)
  surface as an error toast without tearing down the app.
- `AtlasApp` gained injected `provider`/`renderer`/`opener`/`tailoring`/`render_config`
  boundaries + `run_tailor`/`run_cover_letter`/`run_rerender`/`run_open` (each a short
  `session_scope` + the service, mirroring the CLI construction) and an `actions_enabled`
  property. `atlas tui` builds the provider chain + renderer **best-effort**: on
  `ConfigError`/`RenderError`/`LLMError` it launches **browse-only** (read/track screens need no
  AI) with the Tailor actions disabled + an `atlas doctor` hint.
- Tests stay hermetic (AGENTS.md §6.2) by injecting `FakeLLMProvider`/`FakePdfRenderer`/
  `FakeFileOpener` and a `tmp_path` renders dir at the app boundary; the `Pilot` tests drive each
  worker to completion via `await app.workers.wait_for_complete()` and assert the DB result
  (success), that nothing persisted (worker error handled), and that browse-only disables the
  actions. 100% line+branch; `mypy --strict` incl. win32; `uv build` confirms the wheel is
  unchanged in shape. **This closes item #6 — the Phase 1 core loop is complete.**

Phase 1 · Core TUI — `atlas.tui` (Textual) + `atlas tui` (item #6, PR 2 — the browse/track screens):

- `atlas.tui.app.AtlasApp`: the Textual app, owning an **injected engine** (production
  `initialize_database()`, tests the in-memory `db_engine`) and opening a short `session_scope`
  per read/action via `read()` / `change_status()`. Nav bindings + `app.tcss` (shipped in the
  wheel via Hatchling's default packaging, like the render themes).
- Four screens (`atlas.tui.screens`): **Dashboard** (pipeline funnel, active profile, recent
  activity, upcoming deadlines), **Applications** (a `DataTable` table and a Kanban board grouped
  by status, toggleable; Enter opens detail), **Application detail** (status timeline, materials,
  fit, notes; drills into the posting), and **Posting detail** (normalized fields + fit). A shared
  `StatusPickerScreen` modal drives in-TUI status changes through the state machine — a valid move
  updates + toasts, an illegal one shows an error toast.
- The **coverage lever**: all data logic is in pure builders — `atlas.tui.data`
  (`build_dashboard_report`, `build_application_detail`) plus the reused CLI `build_*` — tested
  directly against `db_engine`; the screens are a thin layer exercised by Textual's `Pilot`
  (`asyncio_mode = "auto"`, the project's first async tests). Only the real `app.run()` in the
  `atlas tui` launcher is `# pragma: no cover`, mirroring `RichPrompter`/`default_file_opener`.
- `count_applications_by_status` (`atlas.tracking.repository`) backs the funnel (the one net-new
  query). New deps: `textual` + `pytest-asyncio` (dev). CLI: `atlas tui` (quiets console logging,
  keeps file logging, then launches). 100% line+branch; `mypy --strict` incl. win32; `uv build`
  confirms `app.tcss` ships. Verified end-to-end with `Pilot`: every screen mounts, navigation
  and the table/Kanban toggle work, and a status change persists + toasts (invalid → error). The
  Tailor workspace + background-worker action wiring finish item #6 next.

Phase 1 · Application-tracking core + CLI — `atlas.tracking` + `atlas status`/`apply`/`list`
(item #6, PR 1 — the data foundation for the core TUI):

- `atlas.tracking.status`: the **pure** state machine — `ApplicationStatus` (`StrEnum`
  mirroring `matching.Verdict`, its `.value` persisting into the existing `application.status`
  column), the forward-leaning `ALLOWED_TRANSITIONS` graph (with `Withdrawn` reachable from
  every non-terminal stage and an `Interview` self-edge for successive rounds), `can_transition`,
  `TERMINAL_STATUSES`, and the typed `StatusTransition` history-entry model.
- `atlas.tracking.service`: `set_application_status` validates the move (unless `force=True`),
  appends a timestamped `StatusTransition` to `status_history` (reassigning the list so the JSON
  column is marked dirty), bumps `updated_at`, stamps `applied_at` when the application first
  reaches `applied`, and records `outcome` on a terminal stage — returning a serializable
  `StatusChangeOutcome`. `mark_applied` is the `→ applied` convenience. The clock is injected
  (`utcnow` default) so timestamps are deterministic in tests; lookup reuses
  `atlas.tailor.repository.get_application` (`ApplicationNotFoundError`), and an illegal move
  raises `InvalidStatusTransitionError`.
- `atlas.tracking.repository`: `list_applications(session, *, status=None, profile_id=None)` —
  the net-new query the tracking views need, ordered newest-updated first.
- CLI (`atlas.cli.tracking` + `main`): `atlas status set <id> <stage>` (`--due` / `--force` /
  `--json`), `atlas apply mark <id>` (`--force` / `--json`), and `atlas list`
  (`--status` / `--profile` / `--json`). Pure `build_applications_report` / `render_*` split
  with a `_STATUS_STYLES` palette (mirroring `matching.verdict_style`); the `stage` argument is
  typed `ApplicationStatus` so Typer validates and lists the choices. Unknown id or illegal
  transition (without `--force`) → exit 1. **No migration** — the `application` table already
  had its full §6 column set. 100% line+branch; `mypy --strict` incl. win32. Verified
  end-to-end against a real temp DB: a `preparing` application moves `→ ready → applied`
  (recording `applied_at`), an illegal `→ preparing` jump exits 1 with a clear message,
  `--force` overrides it, and `list`/`--status`/`--json` behave. The first Textual TUI screens
  (§8) finish item #6 in a follow-up PR.

Phase 1 · Cover letter + render/open — `atlas.coverletter` + `atlas.materials` + `atlas.platform`
(item #5, PR 3/3 — **completes item #5**):

- `atlas.coverletter`: mirrors the `atlas.tailor` shape — `CoverLetterDraft` model, the
  honesty-governed `write_cover_letter` AI pass (renders the `write_cover_letter/v1` prompt via
  `complete_json`; propagates `LLMOutputError`), `build_cover_letter_context`, append-only
  versioned `create_cover_letter`/`get_latest_cover_letter`, and the
  `write_application_cover_letter` service. The letter is grounded in the application's latest
  tailored-resume selections if present, else a master-resume summary (`NoMasterResumeError` when
  neither exists); rendered once (a letter is one page) through the new `matching` cover theme;
  `LLMOutputError` → `CoverLetterOutputError`.
- `atlas.render` additions: `CoverLetterContext` view model + `render_cover_letter_html` (a shared
  `_render_theme` helper backs both resume and cover rendering) + the `matching` theme
  (`cover.html.jinja` + `cover.css`, sharing the `jakes-resume` visual language). The
  previously-unconsumed `[render] cover_theme` config is now used.
- `atlas.materials`: `rerender_application` re-renders the latest tailored resume (from stored
  `final_content`) and cover letter (from stored `content`) to fresh PDFs **with no AI**,
  skipping missing materials; `open_application` opens the rendered PDFs via an injected opener.
- `atlas.platform` (new): the `FileOpener` seam — `default_file_opener` dispatches by
  `sys.platform` (`os.startfile` / `open` / `xdg-open`), `# pragma: no cover`; `FileOpenError`
  for missing/failed opens. The first piece of the §12.1 platform-abstraction layer; a
  `FakeFileOpener` keeps the suite hermetic.
- `cover_letter` table + Alembic migration (`down_revision` on the tailoring head);
  `get_application` + `ApplicationNotFoundError` added to `atlas.tailor` for the
  application-keyed commands.
- CLI: `atlas cover <job_id>` (`--tone`), `atlas render <application_id>`, `atlas open
  <application_id>` (top-level commands; `atlas open` needs no AI/renderer). Pure display split in
  `atlas.cli.coverletter` / `atlas.cli.materials`; `--json` throughout; each error → exit 1.
  100% line+branch; `mypy --strict` incl. win32 (the opener's `os.startfile` ignore is
  `unused-ignore`-tolerant). Verified end-to-end with a fake provider + real WeasyPrint: a cover
  letter renders to a valid 1-page PDF, `render` re-renders from stored content, and `open`
  launches the PDFs; the suite injects `FakePdfRenderer`/`FakeFileOpener` so CI never renders or
  opens for real.

Phase 1 · Resume-tailoring engine — `atlas.tailor` + `atlas tailor` (item #5, PR 2/3):

- `atlas.tailor.structure`: pure `TailoredItem` / `TailoredResume` models (the `complete_json`
  target — selection items keyed by `content_id` with reworded text + reasons, plus gaps),
  mirroring `matching.structure`.
- `atlas.tailor.ai_tailor`: `select_and_reword(...)` renders the versioned `select_and_reword`
  prompt (posting + emphasis + honesty level + content-ID-tagged blocks) and drives
  `complete_json`; **propagates `LLMOutputError`** (truth-anchored — the service wraps it).
- `atlas.tailor.blocks`: `tag_blocks_for_prompt` (the `[content_id] (type) text` rendering) and
  `render_blocks` — maps the AI's included items back onto real source blocks **by content_id**,
  dropping any hallucinated id (anti-fabrication guard), producing unpersisted `ResumeBlock`s the
  render pipeline already accepts.
- `atlas.tailor.safety`: `restore_dates` — the deterministic §5.7-step-6 safety net that
  re-appends month-year dates the rework dropped (regex, no LLM), keyed by content_id.
- `atlas.tailor.onepage`: `pack_to_one_page` — the render-measure-**trim** loop (reuses
  `render_resume_html` + the injected `PdfRenderer`), trimming the lowest-priority trailing
  entry until it fits one page or a bounded cap; `enforce_one_page=False` renders once.
- `atlas.tailor.service`: `tailor_posting(...)` — resolve posting/profile/resume → select+reword
  → date-restore → block-map → build context → one-page pack → write PDF → get-or-create
  `Application` + append versioned `TailoredResume` → `TailorOutcome`. `LLMOutputError` →
  `TailoringOutputError`; missing posting/profile/resume raise. All boundaries injected.
- `[tailoring]` config (`TailoringConfig` + `HonestyLevel` enum: `honesty_level` default
  `light_inference`, `enforce_one_page` default `true`) now loads.
- `application` (full §6 columns) + `tailored_resume` tables + an Alembic migration
  (`down_revision` on the match_score head); `tailored_resume` append-only + versioned per
  application, PDF referenced by path.
- `select_and_reword/v1` prompt (`SELECT_AND_REWORD_PROMPT_VERSION`); `.jinja` ships in the wheel.
- CLI (`atlas.cli.tailor` + `main`): `atlas tailor <job_id>` (build provider chain + renderer →
  `tailor_posting` → Rich grid with PDF path / included count / page count / gaps, or `--json`),
  warning on one-page overflow. Unknown id / no profile / no resume / config / AI failure → exit
  1. 100% line+branch; `mypy --strict` incl. win32. Verified the full pipeline end-to-end with a
  fake provider + real WeasyPrint → a valid 1-page PDF with dates restored; the suite injects a
  `SequencedPdfRenderer` so CI never renders for real.

Phase 1 · Rendering-pipeline foundation — `atlas.render` + `atlas resume render` (item #5, PR 1/3):

- `atlas.render.structure` + `context`: pure view models (`ResumeContext` / `ResumeSection` /
  `ResumeEntry`, and `RenderResult` = pdf bytes + measured page count) and
  `build_resume_context(blocks, *, name)` — groups the content-ID'd `ResumeBlock`s by type into
  ordered, titled sections (contact → header; unknown types folded into "Additional" so nothing
  is dropped), normalizing bullet markers.
- `atlas.render.themes` + `themes/jakes-resume/`: a `render_resume_html(context, *, theme)` that
  reads a theme's `resume.html.jinja` + `resume.css` and renders self-contained HTML (CSS inlined;
  `autoescape=True`, `StrictUndefined`). Ships the **`jakes-resume`** theme (the default) — the
  familiar Jake Gutierrez one-page layout (centered name/contact header, ruled section headings,
  two-line entry headers with right-aligned dates/locations, tight bullet lists). A missing
  template or stylesheet → `ThemeNotFoundError`. `.jinja`/`.css` ship in the wheel (verified via
  `uv build`).
- `atlas.render.renderer`: the `PdfRenderer` seam mirroring the scraper's `Fetcher` /
  litellm `CompletionFn` — `default_weasyprint_renderer` (lazy `import weasyprint`, `# pragma: no
  cover`) returns pdf bytes + `len(document.pages)`; `build_renderer(config)` maps `engine` →
  impl (`weasyprint` today; anything else → a clear `RenderError`, so Chromium plugs in later).
- `atlas.render.store`: `write_pdf(...)` writes the PDF under `<data_dir>/renders` (injectable
  dir; referenced by path, never a DB blob, §6), mirroring `scrape.snapshot`.
- `atlas.render.service`: `render_master_resume(session, *, renderer, theme, renders_dir=None)` —
  resolve latest resume + user name → build context → render HTML → render PDF → write →
  `RenderOutcome` (path, page_count, one_page, version, theme). `NoMasterResumeError` when unset.
- `[render]` config (`RenderConfig`: `engine`/`resume_theme`/`cover_theme`) now loads (was an
  ignored block); default `resume_theme = "jakes-resume"`.
- CLI (`atlas.cli.render` + `main`): `atlas resume render` (build renderer from config →
  `render_master_resume` → Rich detail grid / `--json`), warning when the render overflows one
  page (the trim loop lands with tailoring). Invalid config / unsupported engine / no resume →
  exit 1. 100% line+branch; `mypy --strict` incl. win32. Verified the real WeasyPrint path
  produces a valid 1-page PDF; the suite injects a `FakePdfRenderer` so CI never loads WeasyPrint.

Phase 1 · Fit scoring — `atlas.matching` + `score_fit` prompt + CLI (this branch):

- `atlas.matching.structure`: the pure `FitAssessment` (the `complete_json` target — score,
  verdict, rationale, matched strengths / gaps / dealbreaker hits, salary fit) and
  `DeterministicSignals` models, with `Verdict` / `SalaryFit` / `SignalStatus` `StrEnum`s and
  `extra="ignore"` (forward-compatible), mirroring `atlas.scrape.structure`.
- `atlas.matching.signals`: `compute_signals(posting, preferences)` computes the deterministic
  salary / location / work-auth / deal-breaker signals locally (never the LLM), each degrading
  to `UNKNOWN` when the inputs don't support a decision — passed into the prompt as context and
  shown as badges, never used to pre-discard (§5.6).
- `atlas.matching.summary`: `build_resume_summary(blocks)` builds a compact, size-capped
  plaintext summary of the fit-relevant resume blocks for the prompt (the "compact master-resume
  summary" §5.6 asks for).
- `atlas.matching.ai_score`: `score_fit(...)` renders the versioned `score_fit` prompt and drives
  `complete_json` for a `FitAssessment`. Unlike `parse_job_posting`, it **does not** swallow
  `LLMOutputError` — a bogus score would pollute the queue, so it propagates for the service to
  wrap.
- `atlas.matching.repository` + `service`: append-only `create_match_score` /
  `get_latest_match_score`, and `score_posting(session, id, *, provider, clock=utcnow)` —
  resolve posting/active-profile/latest-resume, compute signals, score, persist, return a
  `ScoreOutcome`; precondition failures raise `NoActiveProfileError` / `NoMasterResumeError`,
  and `LLMOutputError` → `ScoringError`. All boundaries injected (provider, clock) so the suite
  is hermetic.
- `score_fit/v1` prompt (`atlas.ai.prompts`, `SCORE_FIT_PROMPT_VERSION`); `.jinja` files ship
  in the wheel (verified via `uv build`).
- `match_score` table (`atlas.db.models`) with an Alembic migration (`down_revision` on the
  job-posting schema); beyond §6 it adds `salary_fit` + a `signals` JSON blob so badges render
  on re-view. `created_at` uses `UtcDateTime`.
- CLI (`atlas.cli.matching` + `main`): `atlas score <id>` (build provider chain like `add` →
  `score_posting` → Rich detail grid with signal badges / `--json`), best-effort scoring wired
  into `atlas add` (scores a new posting in its own transaction; a scoring failure warns and
  keeps the saved posting), and the latest score/verdict surfaced as a Fit column in
  `atlas postings list|show`. Unknown id / no profile / no resume / unusable AI output → exit 1.
  100% line+branch; `mypy --strict` incl. win32. (A pre-existing latent import cycle —
  `profiles.prompt` importing `atlas.cli.console` at module load — was made lazy so the new
  `atlas.matching → atlas.profiles` edge doesn't close the loop.)

Phase 1 · Paste-URL scrape + parse — `atlas.scrape` + `atlas.ai.prompts` + CLI (this branch):

- `atlas.scrape.fetcher`: an injectable `Fetcher` protocol (httpx-backed `default_fetcher`,
  pragma'd; a `FakeFetcher` in the suite) fronts the network, with a `BrowserFetcher` seam for
  the **deferred Playwright** JS-render fallback (no `playwright` dep yet — wired in a later
  step, like the resume parser's AI seam).
- `atlas.scrape.extract` + `ai_extract`: a deterministic ladder — JSON-LD (schema.org
  `JobPosting`) → OpenGraph → main text; a structured posting with a title short-circuits the
  AI, otherwise the **`parse_job_posting` AI pass** runs. This is the **first command-flow
  model call** in Atlas. Per §7 an `LLMOutputError` degrades gracefully (raw text kept as the
  description) so a hard page is still saved.
- `atlas.scrape.repository` + `snapshot` + `service`: pure repo over an open session
  (get-or-create company by name + the single `type="url"` source, dedup by normalized apply
  URL), on-disk raw-HTML snapshots (referenced, never a DB blob), and the `add_posting`
  orchestration (fetch → extract → AI-if-needed → snapshot → persist; idempotent re-add). All
  boundaries injected (fetcher, provider, snapshot dir, clock) so the suite is hermetic.
- `atlas.ai.prompts`: the versioned Jinja2 prompt library §18.1 locks in — `render_prompt`
  loads `system.jinja` + `user.jinja` from `templates/<task>/v<version>/` under a
  `StrictUndefined` env, returning a `RenderedPrompt`. Ships `parse_job_posting/v1`; `.jinja`
  files ship in the wheel (verified via `uv build`).
- `company` / `job_source` / `job_posting` tables (`atlas.db.models`) with an Alembic migration
  (`down_revision` on the master-resume schema); `job_posting.fetched_at`/`posted_at` use
  `UtcDateTime`.
- CLI (`atlas.cli.scrape` + `main`): `atlas add <url>` (build provider chain like `doctor` →
  `add_posting`) and `atlas postings list|show` (Rich table / detail grid + `--json`). Pure
  logic/render/orchestrate split like `resume`; fetch/extraction failures and unknown ids →
  exit 1. 100% line+branch; `mypy --strict` incl. win32. Verified end-to-end (hermetically):
  first add creates the posting + writes a snapshot, re-adding the same URL is a no-op, and
  `postings list`/`show`/`--json` behave.

Phase 1 · Master resume ingest + parse + versioning — `atlas.resume` + CLI:

- `atlas.resume.structure` + `parser`: a deterministic Markdown parser splits the resume into
  ordered, typed `ParsedBlock`s (contact/summary/experience/project/skill/education/…) by
  heading convention. Each block carries a **stable `content_id`** (a truncated SHA-256 of its
  type + normalized text) so an unchanged bullet keeps its id across versions — the
  traceability anchor for fit-scoring/tailoring/honesty. Duplicate identical blocks
  disambiguate via an occurrence index; heading-less input is captured best-effort so nothing
  is dropped. The `parse_master_resume` **AI fallback is deliberately not wired yet**:
  `parse_markdown` exposes a `StructureExtractor` seam (consulted only for heading-less input)
  that the AI extractor fills later with no change to the deterministic path.
- `atlas.resume.repository` + `service`: pure functions over an open `Session` (mirroring
  `atlas.profiles.repository`) plus the ingest/reparse orchestration. Versions are **immutable
  and monotonic**: `apply_set` creates a new version only when the normalized Markdown differs
  from the latest (identical content is a no-op), `apply_reparse` re-versions from the stored
  source, and neither touches earlier versions. The parser and clock are injected so the logic
  is hermetic (`utcnow` is the default clock).
- `master_resume` + `resume_block` tables (`atlas.db.models`) with an Alembic migration
  (`down_revision` on the initial schema). `atlas.db.types.UtcDateTime` makes `created_at`
  round-trip as timezone-aware UTC (SQLite otherwise drops `tzinfo`); every future timestamp
  column uses it.
- CLI (`atlas.cli.resume` + `main`): `atlas resume set <path>` (ingest, version-if-changed),
  `atlas resume reparse` (re-version from stored source), `atlas resume show` (Rich table +
  `--json`). Pure logic/render/orchestrate split like `profile`; missing file → clean error +
  exit 1, not-yet-set resume on `reparse` → exit 1. 100% line+branch; `mypy --strict` incl.
  win32. Verified end-to-end: `set` writes v1, an unchanged re-`set` is a no-op, an edit + `set`
  writes v2, `reparse` writes v3, and `show`/`--json` behave.

Phase 1 · Onboarding & profiles — `atlas.profiles` + CLI:

- `ProfilePreferences` (`atlas.profiles.preferences`): typed, structured per-profile
  preferences covering PROJECT.md §5.2 — target roles/variants, seniority, specializations,
  location/remote posture, compensation, work authorization, company preferences,
  deal-breakers. `StrEnum`s for closed domains; `extra="ignore"` for forward compatibility.
  Serializes into the existing `profile.preferences` JSON column, so **no schema change / no
  migration**. Tailoring emphasis maps to the separate `profile.tailoring_emphasis` column.
- `atlas.profiles.repository`: pure functions over an open `Session` (the caller wraps them in
  `session_scope`) — `get_user`/`upsert_user`, `create_profile`, `list_profiles`, `get_profile`,
  `get_active_profile`, `set_active_profile`, `update_profile`. Enforces the single-user and
  single-active-profile invariants in code (not DB constraints).
- Onboarding wizard (`atlas.profiles.onboarding` + `prompt`): `run_onboarding`/`ask_user`/
  `ask_profile` are pure over an injectable `Prompter` (a two-method free-text/yes-no boundary);
  `RichPrompter` is the real console impl (its interactive I/O the only pragma'd lines). All
  parsing (lists, optional ints, enum tokens) with re-prompting lives in the wizard; `existing`
  answers pre-fill defaults so the same flow drives first-run and edits. A scripted `FakePrompter`
  joins the shared conftest fakes.
- `atlas.db.initialize_database`: migrates to head and returns a ready engine (engine built first
  so a fresh install's data dir exists before Alembic runs; disposed on failure). First production
  caller of `upgrade_to_head`.
- CLI (`atlas.cli.profile` + `main`): `atlas init` (user + first active profile) and
  `atlas profile list|add|edit|use`. Pure report/render split like `doctor` (Rich table +
  `--json` on `list`); missing ids → clean error + exit 1. 100% line+branch; `mypy --strict` incl.
  win32. Verified end-to-end: `atlas init` writes the DB and `profile list`/`--json`/`add`/`use`
  behave.

Phase 0 · Logging — `atlas.logging`:

- `setup_logging` configures the `"atlas"` package logger (`propagate=False`) with a
  `rich.logging.RichHandler` on the shared **stderr** console (records never contaminate
  stdout / `--json`) and a `RotatingFileHandler` under the platformdirs state dir capturing
  `DEBUG`+. Idempotent (replaces only its own handlers); the real handler construction is an
  injectable factory, so the hermetic suite installs a fake and writes no real log file.
- `resolve_level` is a pure resolver with precedence `--log-level` > `-v`/`-vv` >
  `ATLAS_LOG_LEVEL` > `[logging]` config > `WARNING`, skipping malformed values.
- `[logging]` config section (`LoggingConfig`: level, file_enabled, max_bytes, backup_count).
- The Typer top-level callback gained `--verbose`/`-v` + `--log-level` and initializes logging
  before every subcommand (tolerating a bad config so the command still reports the real error).
- First log sites wired: the corrupt probe-cache handler, the migration-failure path, and the
  API error classifier (type-only, no vendor/secret leakage). First use of pytest `caplog`.
  100% line+branch; `mypy --strict` incl. win32. Verified `atlas -v doctor` writes the state-dir
  log while stdout stays clean.

Phase 0 · Data layer — SQLModel + SQLite (WAL) + Alembic (PR #17):

- `atlas.db.engine`: `create_db_engine(url=None)` builds a SQLite engine and applies
  `PRAGMA journal_mode=WAL` + `foreign_keys=ON` on every connection via a `connect` listener
  (WAL enables the daemon-writer / TUI-reader concurrency model, PROJECT.md §4.1). The URL is an
  injectable boundary defaulting to `db_path()` under the platformdirs data dir; file URLs
  create their parent dir, in-memory URLs use a `StaticPool`. Callers own and dispose the engine
  (Windows-safe teardown of the `.db` + `-wal`/`-shm` sidecars).
- `atlas.db.session`: `session_scope(engine)` — a transactional context manager (commit on clean
  exit, roll back + re-raise on error, always close).
- `atlas.db.models`: the foundational table slice — `User` and `Profile` — as SQLModel tables
  with JSON-shaped columns. The remaining PROJECT.md §6 tables grow per-feature in Phase 1.
- `atlas.db.migrate` + `atlas.db.migrations`: an in-process Alembic driver (`alembic_config` /
  `upgrade_to_head`, failures → `MigrationError`) plus the migration environment (targets
  `SQLModel.metadata`) and the initial-schema migration creating `user` + `profile`. Proven
  end-to-end by a test running `upgrade head` against a temp DB; `alembic.ini` is the dev CLI.
- Hermetic tests (in-memory SQLite via a new `db_engine` conftest fixture; migrations run against
  a `tmp_path` DB). New deps `sqlmodel` + `alembic`. `migrations/` excluded from mypy/ruff and
  omitted from coverage; the rest holds 100% line+branch. `mypy --strict` clean (incl. win32).

Phase 0 · AI provider — structured error classification + CLI version floor (PR #14):

- Claude Code adapter switched to `--output-format stream-json --verbose`. Verified against
  the real CLI that the terminal `result` event still carries
  `structured_output`/`result`/`usage`/`total_cost_usd` with `--json-schema`, so the
  structured-output contract is intact; `_parse_response` reads the NDJSON terminal event.
- `_classify_error` maps auth/rate-limit failures from the stream-json structured `error`
  category (`authentication_failed`, `rate_limit`, …), scanning all events, with the stderr
  substring heuristic kept only as a fallback.
- CLI version floor: `parse_cli_version` + `CliAdapter._minimum_version()` /
  `check_availability()` (returns `CliAvailability(available, reason)`); Claude Code pinned to
  ≥ 2.1.205, hard-failed as unavailable when older. `atlas doctor` shows the specific reason
  (e.g. "CLI too old; needs >= 2.1.205"). Resolves PROJECT.md §18.2.
- Verified end-to-end against the real `claude` 2.1.220 (available; probe shows
  json/schema/stream/sys ✓) and a raised floor (hard-fail). 100% line+branch coverage.
- **This completes the AI provider abstraction for Phase 0.**

Phase 0 · AI backend capability probe (PR #13):

- `atlas.ai.probe`: `probe_backend(provider)` runs a tiny "reply OK as JSON against this
  schema" round-trip and reports a `BackendCapabilities` across all five design capabilities —
  JSON output, JSON schema, streaming, system-prompt injection, model override (first two
  deterministic; last three best-effort, documented). Pure over the `LLMProvider` protocol, so
  the hermetic suite drives it with a fake provider and no live call. Any `LLMError` → a
  generic `ok=False` result (no secrets/paths leaked). ≤3 live calls per probe.
- `atlas.ai.probe_cache`: persists `ProbeResult`s (keyed by backend) as JSON under the
  platformdirs cache dir, mirroring the config-loader idiom; a missing/corrupt cache is treated
  as empty, never a crash.
- `atlas doctor` now reports capabilities: bare invocation makes **no** live call and shows
  cached results; `--probe` runs the live (billable) round-trip reusing/persisting the cache;
  `--refresh` re-probes all. Themed capability column; included in `--json`. Verified live
  against the installed `claude` (json/schema/stream/sys ✓, model ✗). 100% line+branch.

Phase 0 · CLI scaffold + `atlas doctor` v1 (PR #12):

- `atlas.cli`: Atlas's Typer command group, exposed via the `atlas` console script
  (`[project.scripts]`) and `python -m atlas`. A top-level callback keeps it multi-command so
  future subcommands (`config`, `init`, the TUI launcher, …) route by name.
- **`atlas doctor`** validates config and reports each configured backend's availability in
  chain order (default + failover): human-readable text or `--json`; exit `0` if any backend
  is usable, `1` if none is (or config/keyring won't load). Pure logic in `atlas.cli.doctor`
  (`run_doctor`/`render_report`) builds each backend via `build_named_provider` and records
  `is_available()`, catching per-backend construction errors so one bad backend doesn't sink
  the report. No live model calls yet — the capability round-trip is deferred.
- `build_named_provider` promoted to public in `atlas.ai.router`. New runtime dep: `typer`.
  100% line+branch coverage (fake runner/keyring for logic; Typer `CliRunner` for the command).

Phase 0 · AI provider abstraction — failover chain (PR #11):

- `atlas.ai.router`: `FailoverProvider` wraps an ordered list of `LLMProvider` backends and
  is itself an `LLMProvider`, so callers stay agnostic. `complete()`/`stream()` try each
  backend in order and fail over on availability-signal errors — `LLMBackendError` (covering
  `LLMAuthError`/`LLMRateLimitError`) and `LLMTimeoutError` — re-raising the last error when
  all fail. `LLMOutputError` is deliberately **not** a trigger: it is a content/schema failure
  surfaced after `complete_json()`'s recovery ladder, so it propagates and stops the walk
  (PROJECT.md §5.1: failover is the last resort after content recovery). An empty chain is
  rejected at construction.
- `build_provider_chain(config, store)` assembles the chain from `AiConfig` (`default_backend`
  then each `failover` name), mapping each to its factory and raising a clear `LLMError` for an
  unknown backend name.
- `build_claude_code_provider` — a config-driven factory for the CLI backend matching
  `build_openrouter_provider`; resolves the `--bare` key via `resolve_api_key` only when
  `use_bare` is set. New schema field `ClaudeCodeBackend.api_key_handle` (default `"anthropic"`).
- No new runtime dep. 100% line+branch coverage via the offline `FakeLLMProvider`.

Phase 0 · AI provider abstraction — OpenRouter/LiteLLM API backend (PR #10):

- `atlas.ai.api`: a single `LiteLLMProvider` implementing `LLMProvider` for every hosted
  backend (OpenRouter, Bedrock, Anthropic, Gemini, …), plus `build_openrouter_provider` — the
  default API failover backend. Maps `LLMRequest`→chat messages, applies a per-provider
  adaptive timeout, normalizes `ModelResponse`→`LLMResponse`/`Usage` (tokens + cost) via
  defensive access (no `litellm` types imported), and classifies failures by HTTP
  status/message into `LLMAuthError`/`LLMRateLimitError`/`LLMTimeoutError`/`LLMBackendError`.
- Two injectable seams keep the heavy `litellm` import out of the hermetic suite (AGENTS.md
  §6.2) and the API path swappable: `CompletionFn` (the `litellm.completion` boundary owning
  the **transport** retry layer via `num_retries` + `drop_params`) and `CapabilityFn`
  (per-model schema support from LiteLLM's **registry, not hardcoded**, so `response_format`
  is requested only where supported and `complete_json()` recovers structure otherwise).
- OpenRouter key via `resolve_api_key()` (keyring first, `OPENROUTER_API_KEY` fallback),
  passed to LiteLLM directly, never via `os.environ`; model auto-prefixed for routing.
- New runtime dep: `litellm`. Reusable offline `FakeChatCompleter`/`FakeModelResponse` test
  doubles in `tests/conftest.py`. 100% coverage; two justified pragmas on the lazy-import
  boundaries.

Phase 0 · Configuration + secrets — `atlas.config` (PR #9):

- Cross-platform paths via `platformdirs` (`config_dir`/`data_dir`/`cache_dir`/`state_dir`/
  `config_file`); no hardcoded `~/.config`.
- Lean, forward-compatible TOML schema (`Config`/`AiConfig`/backends; `extra="ignore"` so a
  fuller user config's not-yet-built sections load) with `load_config`/`save_config`
  (stdlib `tomllib` read, `tomli_w` write; missing file → defaults; bad TOML/values →
  `ConfigValidationError`).
- Keyring-backed secrets: `SecretStore` (handles namespaced under the `atlas` service) +
  a single `resolve_api_key()` (keyring first, optional env fallback local providers can
  disable, keys never written to `os.environ`). Backend selection refuses insecure plaintext
  storage — real OS keychain preferred; headless boxes use the `keyrings.alt` encrypted-file
  backend only when `ATLAS_KEYRING_PASSWORD` is set, else `KeyringUnavailableError`.
- New deps: `keyring`, `platformdirs`, `tomli-w`, `keyrings.alt`, `pycryptodome`. Reusable
  `FakeKeyring` test double in `tests/conftest.py`. 100% coverage; two justified pragmas on
  the real-backend constructors.

Phase 0 · AI provider abstraction — Claude Code adapter (PR #8):

- `ClaudeCodeAdapter` (`src/atlas/ai/cli/claude_code.py`), Atlas's default CLI backend:
  builds `claude -p … --output-format json --json-schema …`, appends a neutralize
  instruction via `--append-system-prompt` and passes no `--allowedTools`, maps the JSON
  envelope onto `LLMResponse` (`structured_output`→`structured`, `result`→`text`, whole
  envelope→`raw`, `usage`+`total_cost_usd`→`Usage`), supports `--bare` + injected
  `ANTHROPIC_API_KEY` (merged env, never logged), and classifies failures as
  `LLMAuthError`/`LLMRateLimitError`/`LLMBackendError` (stderr heuristic).
- `CliAdapter` gained `_env_for` / `_classify_error` hooks; `LLMAuthError` /
  `LLMRateLimitError` added to the error hierarchy. The seam test now runs the real adapter
  through `complete_json`. No new runtime dep (stdlib). 100% coverage.

Phase 0 · AI provider abstraction — `CliAdapter` base (PR #7):

- `atlas.ai.cli` subprocess boundary (`src/atlas/ai/cli/runner.py`): frozen `RunResult`,
  runtime-checkable `SubprocessRunner` protocol, and `default_subprocess_runner`
  (own process group, kills the tree on timeout — the one justified `# pragma: no cover`).
- `CliAdapter` base class (`src/atlas/ai/cli/base.py`): per-call scratch cwd, request-timeout
  enforcement → `LLMTimeoutError`, non-zero-exit → `LLMBackendError`, `is_available()` version
  probe, single-chunk `stream()`; subclasses supply `_build_argv` + `_parse_response`.
- `LLMTimeoutError` / `LLMBackendError` added to the error hierarchy. Reusable offline
  `FakeSubprocessRunner` test double in `tests/conftest.py`. No new runtime dep (stdlib).
  100% coverage, incl. an adapter→`complete_json` end-to-end seam test.

Phase 0 · AI provider abstraction — core contract (PR #6):

- `atlas.ai` package with the `LLMProvider` protocol and `LLMRequest` / `LLMResponse` /
  `Usage` models, plus the `LLMError` / `LLMOutputError` hierarchy (`src/atlas/ai/base.py`).
- `complete_json()` structured-output recovery ladder (`src/atlas/ai/complete_json.py`):
  native structured field → balanced-JSON extraction → bounded content retries with
  temperature escalation → prompt-only fallback → `LLMOutputError`; generic over the
  target Pydantic model, so no `jsonschema` dependency. Reusable offline `FakeLLMProvider`
  test double in `tests/conftest.py`. First runtime dependency: `pydantic`. 100% coverage.

Phase 0 · Repository hygiene & scaffold (foundation every later PR depends on):

- uv project scaffold: `pyproject.toml` (hatchling), committed `uv.lock`, `src/atlas`
  package (`__version__`, `py.typed`), smoke tests — 100% coverage.
- Quality-gate config: `ruff` (format + lint), `mypy --strict`, `pytest` + 100%
  line/branch coverage.
- CI: `.github/workflows/ci.yml` on the Windows/macOS/Linux × Python 3.11–3.13 matrix
  via uv. `main` branch protection requires these checks green.
- `.pre-commit-config.yaml` mirroring the CI gates.
- Repo metadata: PR template (Definition of Done), issue templates, Dependabot,
  CODEOWNERS.
- `CHANGELOG.md` and `CONTRIBUTING.md`.

_(Merged via PR #4. See `git log` and closed PRs for detail.)_

---

## 🧭 How to orient a fresh session

Run these to see live state (this file is the summary; git/gh are the ground truth):

```bash
git log --oneline -15               # recent history
gh pr list --state open             # in-flight work (may need the branch)
gh pr list --state merged --limit 5 # what landed recently
git branch -a                       # existing branches
uv sync                             # install deps into the project venv
uv run pytest                       # confirm the suite is green before changing anything
```

Then: read **this file** → the **[roadmap](./PROJECT.md#15-phased-roadmap)** → the
**PROJECT.md section** for the "Next up" item → **[`AGENTS.md`](../AGENTS.md)** for the
rules, and start on a new branch.

---

## Phase progress at a glance

Detailed checklists live in [PROJECT.md §15](./PROJECT.md#15-phased-roadmap); this is the
high-level state.

| Phase | Title | State |
|---|---|---|
| 0 | Foundations (hygiene/CI · scaffold · config/DB/logging · AI providers) | ✅ **complete** — hygiene/CI · scaffold · config/keyring · data layer (SQLModel/SQLite WAL/Alembic) · logging · AI provider abstraction (core contract · CLI + API backends · failover · `atlas doctor` · capability probe) |
| 1 | Core loop (onboarding · resume · scrape · scoring · tailoring · tracking · TUI) | ✅ **complete** — onboarding · master resume · paste-URL scrape · fit scoring · tailoring + cover letter + rendering · application tracking (state machine + CLI) · full TUI (Dashboard · Applications/Kanban · Application detail · Posting detail · Tailor workspace with background action workers). Optional depth (PR-2b tailoring / interactive editing) deferred |
| 2 | Discovery & background (daemon · ATS · aggregators · Discover queue) | 🚧 in progress — daemon + scheduler ✅ (APScheduler · `[discovery]` config · PID-file lifecycle · score-backlog poll · `atlas daemon start\|stop\|status`); company watchlist + Greenhouse ATS discovery ✅ (`atlas.discovery` registry + adapter · `run_discovery_poll` discover→score in the daemon · `atlas company add\|list` · `atlas discover`); **scored Discover queue in the TUI ✅** (`DiscoverScreen` ranked by fit · tailor/dismiss/save/open-URL · `list_scored_postings` · `queue_status` migration · `UrlOpener` seam); more ATS adapters (Lever/Ashby/Workday), aggregators, multiple profiles, IPC surface next |
| 3 | Scheduling & status intelligence (CalDAV · email scan · Q&A drafting) | ⬜ not started |
| 4 | Polish & depth (analytics · more adapters · scraping · DOCX · encryption) | ⬜ not started |
