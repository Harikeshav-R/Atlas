# AGENTS.md

> Instructions for coding agents (Claude Code, Cursor, Gemini CLI, etc.) working on Project Atlas. Read this file at the start of every session. Follow it.

---

## What this project is

**Project Atlas** is a local-first, open-source Electron desktop app that uses AI agents to discover, evaluate, and apply to jobs on the user's behalf. It's fully agentic: the LLM orchestrates work by calling MCP tools; deterministic code is the tool library, not the orchestrator. Everything runs on the user's machine with BYO-API-key. The product is for non-technical white-collar job seekers — UI quality and safety are non-negotiable.

## Source of truth

There are three documents in the project root. **Read them in order the first time you touch the project:**

1. **`product-plan.md`** — The high-level product: vision, features, user flows, phases, risks. Start here to understand *what* we're building and *why*.
2. **`technical-design.md`** — The detailed engineering design: architecture, harness, MCP servers, database schema, subsystems, conventions, build/release. This is where *how* questions are answered.
3. **`CLAUDE.md`** (this file) — The rules and patterns you follow on every task.

**When `technical-design.md` and `CLAUDE.md` disagree with anything else (including your own instincts), they win.** When those two disagree with each other, stop and ask.

Never invent architecture that isn't in these docs. If you think something is missing or wrong, surface it as a question — do not silently improvise.

---

## Stack at a glance

- **Electron** (latest stable) + **TypeScript 5.x** in strict mode, end-to-end.
- **React 18** + **Vite** (via `electron-vite`) + **Tailwind** + **shadcn/ui** + **Lucide** for the renderer.
- **TanStack Router** + **TanStack Query** + **Zustand** for renderer state.
- **Vercel AI SDK** (`ai` package) for model calls and the agent loop.
- **MCP SDK** (`@modelcontextprotocol/sdk`) for internal MCP servers; **`@playwright/mcp`** for browser automation.
- **better-sqlite3** + **Drizzle ORM** for persistence. Synchronous, main process only.
- **Playwright** (Node-native) for scraping and form filling.
- **Puppeteer** for PDF rendering (separate from Playwright usage).
- **Zod** for every schema (IPC, tool I/O, profile, LLM outputs, config).
- **pnpm** + **Turborepo** workspaces for the monorepo.
- **Vitest** for unit/integration tests, **Playwright Test** for e2e, custom runner for agent evals.
- **pino** for structured logging. **keytar** for secrets.

---

## Quick start

```
pnpm install              # install and rebuild native modules
pnpm dev                  # run Electron in dev mode with HMR
pnpm build                # production build
pnpm test                 # run all tests
pnpm test:unit            # unit tests only
pnpm test:integration     # integration tests only
pnpm test:e2e             # e2e tests
pnpm eval                 # run agent eval suites
pnpm lint                 # ESLint + Prettier check
pnpm format               # Prettier write
pnpm typecheck            # tsc across all packages
pnpm db:migrate           # run pending migrations on dev DB
pnpm db:generate          # generate Drizzle migration from schema change
```

**Before every commit, run: `pnpm typecheck && pnpm lint && pnpm test`.** CI will fail otherwise.

---

## Repo layout (summary)

See `technical-design.md` Section 1 for the full breakdown. Quick map:

```
apps/desktop/             Electron app (main + preload + renderer)
packages/
  harness/                Agent harness — the loop, budget, trace, scoping
  model-router/           Vercel AI SDK wrapper with stage-based routing
  schemas/                Shared Zod schemas — single source of truth for types
  mcp-atlas-*/            Internal MCP servers (db, profile, fs, web, user, stories, cost)
  agents/                 Agent definitions (prompts, tool allowlists, configs)
  db/                     Drizzle schema, migrations, query helpers
  pdf-templates/          CV and cover letter HTML/CSS templates
  scrapers/               Per-platform scraping adapters
  eval/                   Agent eval runner and fixtures
  shared/                 Logger, errors, IDs, time utilities
```

**Where code should live:**
- Business logic that an agent calls → an MCP tool in the appropriate `mcp-atlas-*` package.
- Pure utility used across packages → `packages/shared`.
- Types used across packages → `packages/schemas` (as Zod schemas; TS types are inferred).
- Persistence → `packages/db`.
- Anything the renderer shows → `apps/desktop/renderer`.

**If you don't know where something belongs, ask.** Don't create new top-level packages without approval.

---

## Non-negotiable rules

These are invariants. Violating them breaks the product. No task is worth breaking them for.

### Architecture

1. **The LLM is the orchestrator; code is the tool library.** Do not write hard-coded pipelines that replace agent reasoning. If a capability belongs to an agent, implement it as an MCP tool the agent calls. If it's deterministic plumbing (scheduling, dedup, DB writes), it's code.
2. **Everything the agent touches is an MCP tool.** No direct TypeScript function exposure to agents. All capabilities go through the MCP tool layer with Zod-validated args and returns.
3. **The agent harness owns enforcement.** Budgets, tool scoping, approval gating, kill switches, untrusted-content wrapping, and trace capture happen in the harness, not in prompts. Never "trust the prompt" to enforce a rule.
4. **Workers never touch SQLite.** `better-sqlite3` is synchronous and not process-safe. Workers request data from the main process via IPC. See `technical-design.md` Section 20.
5. **Prompts live in code, not in the database.** System prompts are TypeScript template strings in `packages/agents/src/{agent-name}/prompt.ts`.
6. **The canonical profile is YAML, derived by the Profile Parser Agent.** Don't parse CVs in other parts of the code. Don't add alternative profile formats.

### Safety

7. **Irreversible actions are gated on `atlas-user.request_approval`.** Any tool that submits a form, deletes a file, or sends something irreversibly must be a gated tool. The harness enforces this via the trace's approval events. Read `technical-design.md` Section 11 and 12 before touching the Application Agent or any submission tool.
8. **All scraped/untrusted content must be wrapped in `<untrusted_content>` markers** before reaching the model. Use the `wrapUntrusted` helper. Never put scraped text into a system prompt.
9. **Secrets never appear in logs, traces, or error messages.** Use `keytar` for storage. The log layer has a scrubbing middleware; never disable it. If you're writing a log line that might contain a secret, redact it explicitly.
10. **Electron security hardening is not optional.** `contextIsolation: true`, `nodeIntegration: false`, `sandbox: true`, strict CSP. The renderer never loads remote content. Review `technical-design.md` Section 18 before touching Electron config.

### Code quality

11. **Zod validates every boundary.** IPC channels, MCP tool args/returns, LLM structured outputs, profile YAML, config files, persisted JSON blobs. No `any`. No `as` casts without a comment explaining why.
12. **Errors are structured, not strings.** Extend `AtlasError` from `@atlas/shared`. Never throw strings. Never throw across MCP or IPC boundaries — return `{ ok: false, error }`.
13. **Structured logging only.** Use `pino` from `@atlas/shared`. Every log line has a `component` field. Include `run_id`, `agent`, or `tool` when relevant. No `console.log` in committed code.
14. **Time comes from `@atlas/shared/time`.** Never use `Date.now()` or `new Date()` directly. Tests mock time through the shared module.
15. **IDs come from `newId(prefix)` in `@atlas/shared/ids`.** ULIDs with type prefixes (`run_`, `listing_`, etc.). No UUIDs, no random strings.
16. **Dependencies are injected, not imported from globals.** No singleton exports. This is what makes the harness and MCP servers testable.

### Testing

17. **New code ships with tests.** Unit tests for pure logic, integration tests for anything crossing a module boundary, agent eval fixtures for agent behavior changes.
18. **Mock LLMs, mock network, never mock SQLite.** Tests use a real `better-sqlite3` against an in-memory or temp-file DB.
19. **If you change a prompt, add or update an eval fixture.** Silent prompt changes are the most expensive bugs in this project.

---

## Common tasks

Step-by-step patterns for the most frequent kinds of change. Follow these exactly.

### Add a new MCP tool to an existing internal server

1. Open the server package (e.g., `packages/mcp-atlas-db`).
2. Define Zod schemas for the tool's arguments and return value in `src/tools/{tool-name}.schemas.ts`.
3. Implement the tool in `src/tools/{tool-name}.ts` as a pure function that takes dependencies and returns `{ ok, data } | { ok: false, error }`. Never throw.
4. Register the tool in the server's `createServer()` with a clear description, the Zod schemas, and side-effect disclosure ("this writes to the database" or "this makes a network request").
5. Write unit tests in `src/tools/{tool-name}.test.ts`. Test happy path, validation failures, and at least one error path.
6. If the tool is used by an existing agent, update that agent's tool allowlist in `packages/agents`.
7. Run `pnpm typecheck && pnpm test`.

**Tool design checklist** (from `technical-design.md` Section 7):
- Small and unambiguous — one responsibility per tool.
- Descriptive name (`get_profile`, not `profile`).
- Argument names match the domain (`listing_id`, not `params`).
- Typed, structured errors with machine-readable codes.
- Idempotency key where retries matter.
- Size limits on text responses.
- Side-effect disclosure in the description.

### Add a new agent

1. Create `packages/agents/src/{agent-name}/` with:
   - `prompt.ts` — the system prompt as a template string with placeholders.
   - `schemas.ts` — Zod schemas for the agent's input and expected output.
   - `definition.ts` — the agent definition object (name, prompt, tool allowlist, default model stage, fallback model, budgets, schemas).
   - `index.ts` — exports the definition.
2. Register the agent in `packages/agents/src/registry.ts`.
3. The prompt follows the six-section structure from `technical-design.md` Section 8: Identity → Goal → Tools → Constraints → Output → Untrusted Content Stanza. Do not deviate.
4. Keep the tool allowlist **small** — 5–8 tools max. Weaker models get confused by large toolboxes.
5. Write at least three eval fixtures in `packages/eval/fixtures/{agent-name}/`: a happy-path case, an edge case, and a case that should fail gracefully. Include `expected.yaml` with deterministic assertions (no-forbidden-tool-called, budget-not-exceeded, output-schema-valid) and LLM-as-judge assertions for content quality.
6. Run `pnpm eval -- --suite {agent-name}` and verify the suite passes against the reference model.
7. Update `technical-design.md` Appendix A table if this is a new primary agent.

### Add a database migration

1. Modify the Drizzle schema in `packages/db/src/schema/{table}.ts`.
2. Run `pnpm db:generate` — this produces a new SQL migration file in `packages/db/migrations/`.
3. Inspect the generated SQL. Migrations must be **forward-only** and **idempotent** where possible. Never write a down migration.
4. If the change is destructive (rename, drop, type change), split it across multiple releases: add new column → backfill → switch reads → switch writes → drop old in a later release. See `technical-design.md` Section 15.
5. Test the migration on a copy of a populated dev DB: `pnpm db:migrate` with a backup ready.
6. Add a test that verifies the post-migration schema and data integrity.
7. **Never delete user data in a migration.** If a feature is removed, stop writing to its tables and leave them in place.

### Add an IPC channel

1. Define input and output Zod schemas in `packages/schemas/src/ipc/{namespace}.ts`.
2. Add the channel name to the IPC channel registry. Name it `namespace.verb` (e.g., `runs.kill`, `profile.import`).
3. Implement the handler in `apps/desktop/main/src/ipc/{namespace}.ts`. Wrap logic in try/catch; convert errors to structured `AtlasError` responses.
4. Expose the method in the preload script (`apps/desktop/preload/src/api/{namespace}.ts`) via `contextBridge`.
5. Use the channel from the renderer via a TanStack Query hook in `apps/desktop/renderer/src/hooks/{namespace}.ts`. Cache keys follow `[namespace, verb, ...args]`.
6. Write an integration test that calls the handler directly with valid and invalid payloads.

### Add a UI screen

1. Create a new route file under `apps/desktop/renderer/src/routes/`. TanStack Router picks it up via file-based routing.
2. Build the screen with shadcn/ui components only. Never introduce a new component library.
3. Use TanStack Query for anything coming from the main process. Use Zustand only for UI-local cross-component state.
4. Accessibility is required: keyboard focus on all interactive elements, visible focus rings, ARIA roles on custom widgets, WCAG AA contrast, alt text on images, keyboard-navigable without a mouse. shadcn/ui's Radix primitives give you most of this for free — don't break it.
5. URL state (filters, sort, selected item) goes in TanStack Router search params, not component state. This makes views bookmarkable.
6. Add the route to the sidebar navigation if it should be top-level.

### Add a scraper adapter

1. Create `packages/scrapers/src/{platform}/` with `list.ts`, `fetch.ts`, `canonicalize.ts`, and `adapter.ts` exporting the uniform interface.
2. Implement against the platform's public API where possible (Greenhouse, Ashby, Lever all have structured endpoints — see `technical-design.md` Section 23).
3. Save HTML fixtures in `packages/scrapers/src/{platform}/__fixtures__/` for tests.
4. Write unit tests that parse the fixtures and verify the expected shape.
5. Register the adapter in `packages/scrapers/src/registry.ts` so the scheduler can dispatch to it.
6. Update the `sources` table schema if the adapter needs new config fields.

---

## Testing expectations

Read `technical-design.md` Section 31 for the full strategy. Summary:

- **Unit tests** for pure functions, schemas, tool implementations with mocked deps. Target >80% coverage on `shared`, `schemas`, `db`, and tool implementations.
- **Integration tests** for MCP servers in-process, scraper adapters against fixtures, the harness loop with a fake Model Router, IPC handlers with a test DB.
- **Agent eval tests** for agent behavior. Mandatory for prompt or agent definition changes.
- **E2E tests** with Playwright Test for renderer flows. Use a mock Model Router.
- **Never test against real LLM providers in CI.** Always mock. The eval runner is the one exception — it runs against pinned models and is invoked manually or on release branches.

**Mocking rules:**
- LLMs → mocked (always)
- Network → mocked with fixtures
- Playwright → mocked for unit, real browser against local test server for e2e
- SQLite → never mocked, always real (in-memory or temp file)
- Filesystem → never mocked, always temp directory
- Time → mocked via `@atlas/shared/time`
- keytar → mocked (cross-test pollution in real keychain is painful)

---

## Before you commit

Checklist. Run through all of these:

- [ ] `pnpm typecheck` passes
- [ ] `pnpm lint` passes
- [ ] `pnpm test` passes (unit + integration)
- [ ] New code has tests
- [ ] If prompts changed, eval fixtures updated and `pnpm eval` run locally
- [ ] If DB schema changed, migration generated and tested
- [ ] If a feature changed user-visible behavior, added a changeset (`pnpm changeset`)
- [ ] No `console.log`, no `any`, no unhandled promise rejections
- [ ] No secrets, API keys, or PII in committed fixtures
- [ ] Commit message follows Conventional Commits (`feat:`, `fix:`, `chore:`, `refactor:`, `docs:`, `test:`)

---

## Things to never do

Hard "no" list. If you find yourself wanting to do any of these, stop and ask.

- **Never expose raw SQL to agents.** `atlas-db` tools are parameterized and narrow. No `run_query` tool, no string interpolation into SQL.
- **Never open the SQLite DB from a worker process.** Always go through IPC to main.
- **Never put an API key, password, or user PII in a log line, a trace event payload, an error message, or a test fixture.**
- **Never call `fetch`, `XMLHttpRequest`, or any network API directly from the renderer.** All network goes through main via IPC + MCP tools.
- **Never use `localStorage`, `sessionStorage`, `IndexedDB`, or any browser storage API in the renderer.** State goes through IPC to main, which persists in SQLite.
- **Never use `new Date()` or `Date.now()` directly.** Use `@atlas/shared/time`.
- **Never use `Math.random()` for IDs.** Use `newId(prefix)`.
- **Never bypass the harness to call an LLM directly for agent-like work.** If you need reasoning, it's an agent. Small one-shot extraction calls that don't need tools can use the Model Router directly, but only for non-agentic tasks.
- **Never add a `<script src="https://...">` or `<link href="https://...">` to the renderer.** All assets are bundled.
- **Never disable `contextIsolation`, `sandbox`, or CSP in Electron config.**
- **Never write a tool that takes an arbitrary URL and sends arbitrary data to it.** That's a data exfiltration primitive.
- **Never submit a form in auto-apply code without verifying there's a matching approval event in the trace.** The harness enforces this; don't try to work around it.
- **Never commit real scraped HTML containing a real person's name, email, or resume as a test fixture.** Use synthetic data or scrubbed fixtures.
- **Never invent a new internal MCP server without checking `technical-design.md` Section 6.** The seven servers there are the complete set for v1.
- **Never make the renderer a Node process ("just temporarily, for testing").** It is never a Node process. Not even once.
- **Never use React class components, Redux, or MobX.** The stack is function components + TanStack Query + Zustand.
- **Never add a new top-level dependency without justifying it.** Every new npm package is a maintenance and security burden. Prefer writing 50 lines over adding a 200-KB dependency.
- **Never change a migration file after it's been committed.** Write a new migration that fixes the problem.

---

## When to stop and ask

Do not guess on any of these. Surface a question instead.

- The task requires adding architecture not described in `technical-design.md`.
- The task requires changing a core invariant from the "Non-negotiable rules" section above.
- The task touches the Application Agent, submission tools, or the approval flow — these are high-stakes and mistakes are user-visible.
- The task requires a new MCP server, a new agent, or a new provider adapter.
- The task involves a third-party API not currently integrated.
- The task asks you to store something sensitive (credentials, tokens, PII) and you're not sure how.
- The task requires relaxing a safety rule "just this once."
- The product plan and the technical design disagree on the right approach.
- You find a bug in a core component (harness, IPC, DB) while working on something else.
- The existing tests don't cover the area you're modifying and you can't tell what correct behavior should be.

A question is always cheaper than a rollback.

---

## Style and code quality

- **Small files.** 300 lines is a smell, 500 lines is a bug. Refactor before you can't.
- **Pure functions where possible.** Side effects live at clearly-marked boundaries (IPC handlers, MCP tool bodies, DB writes, PDF renders).
- **Comments explain *why*, not *what*.** If the code is unclear, rewrite it instead of commenting it.
- **No clever code.** Boring, obvious code wins. This project will be maintained by a solo dev over years.
- **No premature abstractions.** Wait for three concrete examples before extracting a shared abstraction.
- **Early returns over nested ifs.**
- **`async`/`await` over promise chains.**
- **Never swallow errors silently.** Every catch either handles the error meaningfully, logs it, or returns it as a structured result.
- **Descriptive variable names.** `listing` not `l`, `evaluationResult` not `res`. The only acceptable short names are standard conventions (`i`, `ctx`, `err`, `fn`).
- **Prefer `readonly` and `const` arrays** for anything that shouldn't be mutated.
- **Avoid `enum`** — use union string literal types. Enums in TS have subtle pitfalls.
- **Avoid `namespace`** — use modules.

---

## Security checklist (for anything touching browser, filesystem, or network)

Before submitting code that does any of these, verify:

- [ ] Electron renderer config still has `contextIsolation: true`, `nodeIntegration: false`, `sandbox: true`.
- [ ] CSP header is still set and has not been loosened.
- [ ] No new `<script>` or `<link>` loading from remote URLs.
- [ ] All file paths are resolved against the sandbox roots in `atlas-fs`.
- [ ] All URLs in `atlas-web.fetch` are validated against the configured rate limits and (if applicable) domain allowlists.
- [ ] Any new MCP tool that causes an irreversible effect is marked as gated in its server registration.
- [ ] Any new secret is stored via `keytar` with the `atlas/{category}/{identifier}` naming convention.
- [ ] No secret is logged, traced, or included in an error message.
- [ ] New IPC channels validate input on main and validate output on renderer — both sides.
- [ ] New handlers wrap logic in try/catch and return structured errors, never throw across the IPC boundary.

---

## Glossary (quick reference — full version in `technical-design.md` Appendix C)

- **Agent** — a declarative config (prompt + tool allowlist + model stage + budgets) instantiated per run by the harness.
- **Harness** — the code that runs agents with budget enforcement, trace capture, tool scoping, and approval gating.
- **MCP** — Model Context Protocol. The standard tool interface agents use.
- **Run** — one agent invocation with its trace, budget, and result. Atomic unit of agent work.
- **Trace** — the sequence of events during a run. Unit of debugging.
- **Scope** — a structured string identifying what an approval authorizes.
- **Gated tool** — a tool requiring a matching prior approval in the run trace.
- **Stage** — a category of model use (triage, evaluation, generation, verification, navigation, interaction). Users map stages to models.
- **Canonical profile** — the YAML document that's the single source of truth for the user's self-description.
- **HITL** — human-in-the-loop. Default mode; irreversible actions require explicit user approval.
- **YOLO** — scoped per-batch mode where approvals are auto-granted after a visible delay.

---

## Final note

This project's success depends on agentic behavior working reliably and safely. The rules above are not bureaucracy — every one exists because the alternative is a bug that the user experiences as "the app submitted my application to the wrong job" or "I spent $200 on Claude overnight." Keep the user safe and in control. When in doubt, default to caution, approval, and asking.

If anything in this file is unclear, surface it as a question in your response instead of guessing. Guessing on Atlas is expensive.
