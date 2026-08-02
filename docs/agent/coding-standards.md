# Coding Standards

Conventions for Atlas code. The enforced gates (ruff, mypy --strict, coverage) are defined in
[`AGENTS.md` §5–§6](../../AGENTS.md#5-quality-gates); this doc covers the how-to-write-it that
sits above them.

## Language & typing

- Python **3.11+**. Managed with **uv** (`uv run`, `uv add`, `uv sync`) — never bare `pip`.
- **Full type hints on every function** (params and return). `mypy --strict` must pass with
  zero errors. No `Any` escape hatches without a justified comment.
- Prefer `pydantic` / `SQLModel` models over loose dicts at boundaries.

## Style

- **Match the surrounding code** — naming, structure, comment density, idioms.
- `ruff format` + `ruff check` clean. Don't hand-format against the formatter.
- Small, composable functions. Keep pure logic free of I/O; inject boundaries (clock,
  subprocess runner, HTTP client, DB session) so it's testable.
- Docstrings on every public module/class/function (part of Definition of Done).

## Errors & logging

- **Fail loudly with clear, specific errors.** Don't swallow exceptions.
- **Log details server-/daemon-side; return/surface generic messages to the user** — don't
  leak internals, paths, or secrets into user-facing output.
- Use appropriate log levels; no stray `print`.

## CLI output (pretty & consistent — always)

- **Every CLI command renders through [Rich](https://rich.readthedocs.io/)** — tables,
  panels, themed color, progress bars — never bare `print`/`typer.echo` of unstyled text.
  Aim for the polish of `atlas --help`.
- **One console, one theme.** Render through the shared `console` and `ATLAS_THEME` in
  [`atlas/cli/console.py`](../../src/atlas/cli/console.py) so output is consistent across the
  whole app. Use **semantic** style names (`success`, `error`, `heading`, `accent`, `muted`,
  `ok`, `bad`) — never hard-code colors in a command. Add a new semantic style to the theme
  rather than inlining a color, so the palette stays centralized.
- **Errors/diagnostics → the stderr console**; keep stdout clean for the primary result.
- **Machine-readable output stays plain.** `--json` (and similar) must be unstyled and
  pipe-safe — emit via `print_json_line`, not the styled path. Keep the pure
  data/report-building logic separate from rendering so it's testable without a terminal
  (render Rich objects through the shared console's `capture()` in tests).
- The **TUI** is Textual; this convention governs the **Typer CLI**.

## Secrets & privacy

- **Secrets never in code, config files, logs, or tests.** Use the keyring abstraction.
- API keys pass to LiteLLM directly, **never via `os.environ`**; local providers skip the
  env-key fallback (see [llm-integration.md](./llm-integration.md)).
- Be deliberate about what goes into a prompt; use the PII redactor for tasks that don't need
  contact details.

## Cross-platform (Windows · macOS · Linux — all first-class)

- Use **`platformdirs`** for config/data/cache paths — never hardcode `~/.config`.
- Isolate OS-specific calls (paths, keyring backend, daemon install, notifier, file-open)
  behind the platform layer. No shell-specific assumptions.
- Guard genuinely platform-specific branches; if a line can't be covered on all OSes, use a
  **justified** `# pragma: no cover` (see testing-strategy).

## Data handling

- `copy.deepcopy()` before mutating shared/cached structures.
- SQLite stores structured data + file references; large artifacts (PDFs, HTML snapshots) go
  on disk, not in the DB.
- Any schema change ships with an Alembic migration in the same PR.

## Mutability of AI output

- Treat model output as untrusted: validate against the task schema, run `complete_json()`
  recovery, and run the deterministic safety nets before persisting tailored content.
