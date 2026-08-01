# Testing Strategy

The enforced bar lives in [`AGENTS.md` §6](../../AGENTS.md#6-testing); this doc is the
practical how-to. Design-level testing notes: [PROJECT.md §16](../PROJECT.md#16-testing--quality).

## The bar (non-negotiable)

- **100% line AND branch coverage**, enforced in CI:
  ```bash
  uv run pytest --cov=atlas --cov-branch --cov-report=term-missing --cov-fail-under=100
  ```
- Untestable lines may use `# pragma: no cover` **only with a one-line justification**
  (e.g. an OS-specific branch exercised on another runner). Prefer refactoring for
  testability over excluding.
- Tests are **"anti-theater"**: they must fail when the target behavior breaks. No assertions
  that can't fail.

## Isolation (default suite is hermetic)

No real network, no real coding-CLI subprocesses, no real credentials, no wall-clock/random
dependence. At each boundary:

| Boundary | In tests |
|---|---|
| AI backend | **Fake `LLMProvider`** returning canned structured responses |
| HTTP (scrape/ATS/aggregator/LiteLLM) | **`respx`** + recorded fixtures |
| Database | temp / in-memory SQLite (run migrations against it) |
| Filesystem | `tmp_path` |
| keyring / calendar / email / notifier | fakes; assert on calls, not external effects |
| time / randomness | injected clock / seed |

## Test markers

Mirror the reference project's split:

- `unit` — pure logic, fully isolated.
- `service` — a component with its boundaries faked.
- `integration` — multiple Atlas components together, still no real external I/O.
- `eval` — **real-LLM** checks. **Excluded from the default run**; skipped without a
  configured key. Never let a live call into `unit`/`service`/`integration`.

Default `pytest` runs everything except `eval`.

## What to test (beyond the happy path)

- Failure paths: malformed/truncated AI JSON + the `complete_json()` repair/fallback ladder,
  timeouts, auth failures, empty results, dedup collisions, one-page overflow/underflow.
- **Honesty + safety nets**: claims trace (or fail to trace) to master blocks; date-precision
  restore and personal-info/skills/custom-section preservation fire correctly.
- Every conditional branch (that's what 100% branch coverage forces — don't game it).
- Renderer snapshot tests assert one-page output per theme.
- TUI flows via Textual's test harness (onboard, tailor, status move).

## Local commands

```bash
uv run ruff format --check .
uv run ruff check .
uv run mypy --strict .
uv run pytest            # + coverage gate
```

`pre-commit` runs the fast subset locally; CI runs the full suite on Windows/macOS/Linux.
Do **not** bypass hooks (`--no-verify` is disallowed).
