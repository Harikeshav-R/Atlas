# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

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
