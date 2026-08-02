# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

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

[Unreleased]: https://github.com/Harikeshav-R/Atlas/commits/main
