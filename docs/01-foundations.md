# 01 — Foundations

> Repo layout, runtime topology, and the cross-cutting conventions every other document assumes. Load this on every task.

For the product-level "what and why," see `product-plan.md`. For the rules you must follow on every task, see `CLAUDE.md`. For the document map, see `docs/00-index.md`.

---

## 1. Repository layout

Atlas is a **pnpm monorepo** with workspaces. The choice of pnpm (vs. npm or yarn) is deliberate: it has the best disk and install-time characteristics for monorepos, strict dependency resolution that catches phantom-dependency bugs, and excellent Electron compatibility. Yarn berry's PnP is incompatible with several native modules Atlas depends on (including `better-sqlite3`).

The top-level structure:

```
atlas/
  apps/
    desktop/              Electron app (main + preload + renderer)
  packages/
    harness/              Agent harness — the loop, budget, trace, scoping
    model-router/         Thin wrapper around Vercel AI SDK
    schemas/              Shared Zod schemas (profile, IPC, tool I/O, events)
    mcp-atlas-db/         Internal MCP server for SQLite access
    mcp-atlas-profile/    Internal MCP server for canonical profile access
    mcp-atlas-fs/         Internal MCP server for sandboxed file I/O
    mcp-atlas-web/        Internal MCP server for web search and fetch
    mcp-atlas-user/       Internal MCP server for user interaction (approval/ask)
    mcp-atlas-stories/    Internal MCP server for Story Bank access
    mcp-atlas-cost/       Internal MCP server for budget introspection
    agents/               Agent definitions (prompts, tool allowlists, configs)
    db/                   Drizzle schema, migrations, query helpers
    pdf-templates/        CV and cover letter HTML/CSS templates
    scrapers/             Per-platform scraping adapters (Greenhouse, Ashby, ...)
    eval/                 Agent evaluation runner and fixtures
    shared/               Cross-cutting utilities (logger, errors, ids, time)
  tools/
    scripts/              Build, release, migration scripts
  docs/                   Technical documentation (this folder)
  .changeset/             Versioning for package releases
  turbo.json              Turborepo pipeline for incremental builds
  product-plan.md         Product-level design (what/why)
  CLAUDE.md               Rules for coding agents
```

Each package has its own `package.json`, `tsconfig.json`, and (where applicable) `vitest.config.ts`. The root has a base `tsconfig.base.json` that individual packages extend.

**Turborepo** manages the build graph — `turbo build` builds packages in dependency order, caches results, and skips unchanged work. This matters more than it sounds on a solo project: a cold build of everything is slow, a warm build is instant, and turbo makes that difference automatic.

**One-repo-one-license**: the whole thing ships under a single OSS license (AGPL v3 — see project README for details).

---

## 2. Runtime topology

Atlas has three kinds of processes at runtime, plus external child processes for MCP servers like Playwright.

**Main process (Electron main).** One instance. Lifecycle: starts when the app launches, exits when the app quits. Owns the SQLite database, the scheduler, the worker pool, the model router, and all MCP servers (internal and external). Also hosts the harness instances for any agents running in-process (small, cheap ones like Triage).

**Renderer process (Electron renderer).** One instance per window, and in practice one window. Runs React + the UI. Has zero Node access — `nodeIntegration: false`, `contextIsolation: true`, `sandbox: true`. Talks to the main process exclusively through typed IPC channels exposed via `contextBridge` in a preload script.

**Worker processes (Electron `utilityProcess`).** Spawned on demand by the main process for heavy or parallelizable work: deep evaluation agents, scraping batches, PDF generation under load. Each worker has its own Node runtime, its own memory, and can crash independently. **Workers cannot touch the database directly** — they request data through a narrow RPC surface back to the main process, which owns the DB connection. This is important: `better-sqlite3` is synchronous and not safe to share across processes.

**External MCP server process (Playwright MCP).** The Playwright MCP server runs as a separate child process spawned by the main process over stdio. It's treated the same way as any other MCP server from the harness's perspective.

**The rule:** if something writes to the database or holds long-lived state, it runs in the main process. If it's CPU-heavy or might crash, it runs in a worker. The renderer does nothing except render.

For details on the worker pool design, see `docs/04-app-shell.md §4`.

---

## 3. Cross-cutting conventions

These conventions apply everywhere. Getting them right on day one saves enormous pain later.

### Naming

- TypeScript packages use `kebab-case` folder names and `@atlas/name` module names.
- Files are `kebab-case.ts`.
- Types are `PascalCase`. Functions and variables are `camelCase`. Constants are `SCREAMING_SNAKE_CASE`.
- Database tables and columns are `snake_case`.
- IPC channels are `namespace.verb` — e.g., `profile.import`, `runs.start`, `approvals.respond`.
- Tool names exposed by MCP servers are `namespace.verb` too — e.g., `atlas-db.get_profile`, `playwright.click`.

### IDs

Everything persistent gets a **ULID**, not a UUID. ULIDs sort lexicographically by creation time, which makes them far more useful for debugging and for database clustered indexes. The shared package exports a single `newId(prefix)` function that returns strings like `run_01HXYZ...` or `listing_01HXYZ...`. Prefixes make IDs self-describing in logs and traces.

Never use `Math.random()`, `crypto.randomUUID()`, or any other ID generator. Always `newId(prefix)`.

### Time

All timestamps are stored as **ISO 8601 strings in UTC**. The shared package exports a single `now()` function (so tests can mock it) and parsing helpers. **Never use `Date.now()` or `new Date()` directly outside of the shared time module.**

### Errors

Errors are **structured, not strings**. The shared package defines a base `AtlasError` class with:
- `code` — a machine-readable identifier like `profile.parse_failed`
- `message` — human-readable
- `cause` — optional underlying error

Every error that crosses a module boundary is an `AtlasError` subclass. Tools returning errors over MCP serialize them as `{ ok: false, error: { code, message } }`. **Never throw across MCP or IPC boundaries** — always return structured errors.

### Logging

`pino` with a file transport that writes structured JSON to `{userData}/logs/atlas.log` with daily rotation. Every log line has a `component` field and optionally a `run_id`, `agent`, or `tool` field for correlation.

Log levels:
- `trace` for tool call internals
- `debug` for routine operations
- `info` for user-visible events
- `warn` for recoverable problems
- `error` for failed operations
- `fatal` for crashes

Default production level is `info`; a developer toggle in Settings flips it to `debug`.

**No `console.log` in committed code.** Use the logger.

### Validation

**Zod everywhere.** Every IPC channel has a Zod schema for its input and its output. Every MCP tool has a Zod schema for its arguments and its return value. The canonical profile has a Zod schema. LLM structured outputs are parsed with Zod. The rule: **data that crosses a trust or process boundary is validated with Zod**.

Schemas live in `packages/schemas/`. TypeScript types are inferred from them, never declared separately. If a type and a schema disagree, the schema is the source of truth.

### Async

`async/await` everywhere; no bare promise chains. Every `await` that can reject is either wrapped in a try/catch or in a `Result`-returning helper. The shared package exports a small `tryCatch` utility that wraps a promise and returns `{ ok: true, value } | { ok: false, error }` so hot paths don't need try/catch boilerplate.

### Immutability

State objects passed between modules are treated as immutable. When mutation is needed, create a new object. This is a discipline, not enforced by the type system (Immer is too much machinery for this project).

### No magic globals

No singletons exported from modules. Dependencies are injected into constructors or function signatures. This matters for testability — the harness needs to be runnable in tests with a fake model router and fake tools.

### Style summary

- Small files. 300 lines is a smell. 500 lines is a bug. Refactor before you can't.
- Pure functions where possible. Side effects are isolated to clearly-marked boundaries (IPC handlers, MCP tool implementations, DB writes).
- Comments explain *why*, not *what*. Code says what.
- No clever code. Boring, obvious code is better than clever code on a project you'll maintain alone for years.
- Avoid abstractions until you have three concrete examples.
- No `enum` — use union string literal types.
- No `namespace` — use modules.
- Avoid `any`. No `as` casts without a comment explaining why.

---

## 4. Where code should live

- **Business logic that an agent calls** → an MCP tool in the appropriate `mcp-atlas-*` package. See `docs/02-agent-runtime.md §6`.
- **Pure utility used across packages** → `packages/shared`.
- **Types used across packages** → `packages/schemas` (as Zod schemas; TS types inferred).
- **Persistence** → `packages/db`. See `docs/03-persistence.md`.
- **Anything the renderer shows** → `apps/desktop/renderer`. See `docs/04-app-shell.md §5`.
- **Agent definitions (prompts, allowlists, budgets)** → `packages/agents`. See `docs/02-agent-runtime.md §4`.
- **Per-platform scraping** → `packages/scrapers`. See `docs/05-subsystems-discovery-evaluation-generation.md §3`.
- **PDF templates** → `packages/pdf-templates`. See `docs/07-delivery.md §5`.
- **Eval fixtures** → `packages/eval`. See `docs/02-agent-runtime.md §13`.

If you don't know where something belongs, ask. Don't create new top-level packages without approval.
