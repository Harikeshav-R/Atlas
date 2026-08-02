# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

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

- **Claude Code adapter now drives `--output-format stream-json --verbose`**
  instead of `--output-format json`. The terminal `result` event still carries
  `structured_output`/`result`/`usage`/`total_cost_usd` (verified against the
  real CLI), so the structured-output contract is unchanged — but failures now
  carry a **structured `error` category** (`authentication_failed`, `rate_limit`,
  …), so `_classify_error` maps auth/rate-limit failures from that category
  rather than string-matching stderr (the stderr heuristic remains a fallback).

[Unreleased]: https://github.com/Harikeshav-R/Atlas/commits/main
