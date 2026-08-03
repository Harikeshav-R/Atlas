# Atlas — Project Status (start here)

> **New session? Read this file first, then [`AGENTS.md`](../AGENTS.md).** This is the
> single "you are here / do this next" pointer. It tells a fresh coding-agent (or human)
> session where the project stands and what to pick up, without reverse-engineering it
> from git history.
>
> **Keep it current.** Updating this file is part of the [Definition of Done](../AGENTS.md#8-definition-of-done):
> whenever a roadmap item lands, tick it here and move the "Next up" pointer. A stale
> STATUS.md is a bug.

- **Last updated:** 2026-08-03 (master-resume ingest/parse/versioning landed —
  **Phase 1 item #2 done**; paste-URL scrape is next)
- **Current phase:** Phase 1 — Core loop 🚧 (onboarding ✅ · master resume ✅ **done**)
- **Design source of truth:** [`docs/PROJECT.md`](./PROJECT.md) — especially the
  [phased roadmap](./PROJECT.md#15-phased-roadmap).
- **Working agreement:** [`AGENTS.md`](../AGENTS.md) (branching, commits, tests, PR flow).

---

## ▶ Next up (do this next)

**Phase 1 item #2 (master resume ingest + parse + versioning) has landed** — see "What has
landed". The `atlas.resume` package (deterministic Markdown parser into content-ID'd blocks
behind an AI-fallback seam, immutable monotonic versions, repository + ingest/reparse
service), the `atlas resume set|reparse|show` commands, and the `master_resume` /
`resume_block` tables are in. **Do #3 next: paste-URL scrape + parse** (§5.5) — turn a
user-pasted job URL into a normalized `JobPosting` (static `httpx` fetch + Playwright
fallback; JSON-LD/OpenGraph/ATS DOM extraction, then an AI extraction pass), storing a raw
snapshot. It feeds the fit-scoring and tailoring steps that follow. Remaining Phase 1 order:

1. ✅ **Onboarding Q&A + preferences** (single profile; schema is already multi-profile) — `atlas.profiles`.
2. ✅ **Master resume ingest + parse + versioning** — `atlas.resume`.
3. **Paste-URL scrape + parse** (static + Playwright fallback) — `atlas.scrape`. ← **do this next**
4. **Fit scoring** for a pasted job — `atlas.matching`.
5. **Resume tailoring + cover letter + HTML→PDF** with one-page enforcement.
6. **Application tracking** + the core TUI screens.

> **Note for #3+:** the AI provider abstraction is fully built but **not yet wired to any
> command**. The resume parser leaves a `StructureExtractor` seam (`atlas.resume.parser`) for
> its `parse_master_resume` AI fallback; the scrape step's AI extraction pass is the natural
> place to make the first real command→model call (`complete_json` + `build_provider_chain`).

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

Phase 1 · Master resume ingest + parse + versioning — `atlas.resume` + CLI (this branch):

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
| 1 | Core loop (onboarding · resume · scrape · scoring · tailoring · tracking · TUI) | 🚧 in progress — onboarding ✅ · master-resume ingest/parse/versioning ✅; paste-URL scrape next |
| 2 | Discovery & background (daemon · ATS · aggregators · Discover queue) | ⬜ not started |
| 3 | Scheduling & status intelligence (CalDAV · email scan · Q&A drafting) | ⬜ not started |
| 4 | Polish & depth (analytics · more adapters · scraping · DOCX · encryption) | ⬜ not started |
