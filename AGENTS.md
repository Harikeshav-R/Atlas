# CLAUDE.md

> Instructions for coding agents (Claude Code, Cursor, Gemini CLI, etc.) working on Project Atlas. Read this file at the start of every session. Follow it.

---

## What this project is

**Project Atlas** is a local-first, open-source Electron desktop app that uses AI agents to discover, evaluate, and apply to jobs on the user's behalf. It's fully agentic: the LLM orchestrates work by calling MCP tools; deterministic code is the tool library, not the orchestrator. Everything runs on the user's machine with BYO-API-key. The product is for non-technical white-collar job seekers — UI quality and safety are non-negotiable.

---

## Documentation structure — read this carefully

The technical documentation is split across multiple files in `docs/` so that you only load the documents relevant to your current task. **Loading every doc on every task wastes context and degrades your performance. Load selectively.**

### Always load on every session

1. **`product-plan.md`** (project root) — The high-level product: vision, features, user flows, phases, risks. Read once at the start of any session to understand _what_ Atlas is and _why_ it exists. You don't need to re-read it every task, but you should have it in context for the first task of a session.
2. **`CLAUDE.md`** (this file) — The rules and patterns you follow on every task.
3. **`docs/00-index.md`** — The router. Tells you which technical documents to load for which task.
4. **`docs/01-foundations.md`** — Repo layout, runtime topology, cross-cutting conventions (IDs, time, errors, logging, validation, naming). **Every other technical doc assumes these conventions. Load this on every task that touches code.**

### Load based on the task

The other documents are loaded _only when the task requires them_. Use the table in `docs/00-index.md` to decide. The full document map:

| #   | File                                                    | Scope                                                                                                                                                                |
| --- | ------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 02  | `docs/02-agent-runtime.md`                              | Agent harness, Model Router, MCP tool library, tool design, prompt engineering, budgets, traces, approval flow, prompt injection defense, agent evaluation framework |
| 03  | `docs/03-persistence.md`                                | Database schema, migrations, file system layout, secrets management                                                                                                  |
| 04  | `docs/04-app-shell.md`                                  | Electron security hardening, IPC layer, worker pool, renderer architecture                                                                                           |
| 05  | `docs/05-subsystems-discovery-evaluation-generation.md` | Canonical profile schema, discovery, evaluation, CV/cover letter generation                                                                                          |
| 06  | `docs/06-subsystems-application-stories-negotiation.md` | Application engine, story bank, negotiation, scheduler, notifications                                                                                                |
| 07  | `docs/07-delivery.md`                                   | Testing, build/packaging/release, observability, dev workflow, PDF pipeline, first-run UX, runbook                                                                   |
| 08  | `docs/08-reference.md`                                  | Quick-reference tables, out-of-scope list, glossary                                                                                                                  |

### Loading protocol

When you receive a task, follow this protocol:

1. **Identify the task type.** Is it adding a tool, building a UI screen, fixing a bug in the Application Agent, writing a migration, etc.?
2. **Open `docs/00-index.md`** and find the matching row in the "Task → required reading" lookup table.
3. **Load the documents listed there**, plus `docs/01-foundations.md` (always), plus `product-plan.md` if you don't already have product context.
4. **Do not load other docs unless you discover during the task that you need them.** If you find a cross-reference like "see `docs/03-persistence.md §4`," decide based on whether the missing context actually matters for what you're doing — load it if it does, skip if it doesn't.
5. **Never load all eight docs at once "just to be safe."** That defeats the purpose of the split and burns your context budget.

### Document priority when in conflict

- **`technical-design` documents and `CLAUDE.md` win over your training intuitions.** When you think "I would normally do X" and a doc says "do Y," do Y.
- **`CLAUDE.md` wins over technical docs only on the rules listed below as "Non-negotiable rules."** For everything else, technical docs are the detailed authority.
- **When two technical docs disagree**, stop and ask. Don't pick one silently.
- **When you think a doc is wrong or missing something**, surface it as a question. Do not improvise.

### Cross-references

Documents reference each other as `docs/02-agent-runtime.md §11` (read as "section 11 of the agent runtime doc"). When you see a cross-reference:

- If the referenced section is essential to your task, load that doc.
- If it's tangential, skip it.
- Section numbers are stable within a doc; if you find a stale cross-reference, fix it in the same PR you're working on.

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

## Where code lives (quick map)

Full layout in `docs/01-foundations.md §1`. Quick map:

- **Business logic an agent calls** → an MCP tool in `packages/mcp-atlas-*`
- **Pure utility used across packages** → `packages/shared`
- **Types used across packages** → `packages/schemas` (as Zod schemas)
- **Persistence** → `packages/db`
- **Renderer code** → `apps/desktop/renderer`
- **Agent definitions** → `packages/agents`
- **Per-platform scraping** → `packages/scrapers`
- **PDF templates** → `packages/pdf-templates`
- **Eval fixtures** → `packages/eval`

If you don't know where something belongs, ask. Don't create new top-level packages without approval.

---

## Non-negotiable rules

These are invariants. Violating them breaks the product. No task is worth breaking them for.

### Architecture

1. **The LLM is the orchestrator; code is the tool library.** Do not write hard-coded pipelines that replace agent reasoning. If a capability belongs to an agent, implement it as an MCP tool the agent calls. If it's deterministic plumbing (scheduling, dedup, DB writes), it's code. Details: `docs/02-agent-runtime.md`.
2. **Everything the agent touches is an MCP tool.** No direct TypeScript function exposure to agents. All capabilities go through the MCP tool layer with Zod-validated args and returns. Details: `docs/02-agent-runtime.md §6`.
3. **The agent harness owns enforcement.** Budgets, tool scoping, approval gating, kill switches, untrusted-content wrapping, and trace capture happen in the harness, not in prompts. Never "trust the prompt" to enforce a rule. Details: `docs/02-agent-runtime.md §1`.
4. **Workers never touch SQLite.** `better-sqlite3` is synchronous and not process-safe. Workers request data from the main process via IPC. Details: `docs/04-app-shell.md §3`.
5. **Prompts live in code, not in the database.** System prompts are TypeScript template strings in `packages/agents/src/{agent-name}/prompt.ts`. Details: `docs/02-agent-runtime.md §8`.
6. **The canonical profile is YAML, derived by the Profile Parser Agent.** Don't parse CVs in other parts of the code. Don't add alternative profile formats. Details: `docs/05-subsystems-discovery-evaluation-generation.md §1`.

### Safety

7. **Irreversible actions are gated on `atlas-user.request_approval`.** Any tool that submits a form, deletes a file, or sends something irreversibly must be a gated tool. The harness enforces this via the trace's approval events. **Read `docs/02-agent-runtime.md §11` and `§12` before touching the Application Agent or any submission tool.**
8. **All scraped/untrusted content must be wrapped in `<untrusted_content>` markers** before reaching the model. Use the `wrapUntrusted` helper. Never put scraped text into a system prompt. Details: `docs/02-agent-runtime.md §12`.
9. **Secrets never appear in logs, traces, or error messages.** Use `keytar` for storage. The log layer has a scrubbing middleware; never disable it. Details: `docs/03-persistence.md §4`.
10. **Electron security hardening is not optional.** `contextIsolation: true`, `nodeIntegration: false`, `sandbox: true`, strict CSP. The renderer never loads remote content. Details: `docs/04-app-shell.md §1`.

### Code quality

11. **Zod validates every boundary.** IPC channels, MCP tool args/returns, LLM structured outputs, profile YAML, config files, persisted JSON blobs. No `any`. No `as` casts without a comment explaining why.
12. **Errors are structured, not strings.** Extend `AtlasError` from `@atlas/shared`. Never throw strings. Never throw across MCP or IPC boundaries — return `{ ok: false, error }`.
13. **Structured logging only.** Use `pino` from `@atlas/shared`. Every log line has a `component` field. Include `run_id`, `agent`, or `tool` when relevant. No `console.log` in committed code.
14. **Time comes from `@atlas/shared/time`.** Never use `Date.now()` or `new Date()` directly. Tests mock time through the shared module.
15. **IDs come from `newId(prefix)` in `@atlas/shared/ids`.** ULIDs with type prefixes (`run_`, `listing_`, etc.). No UUIDs, no random strings.
16. **Dependencies are injected, not imported from globals.** No singleton exports. This is what makes the harness and MCP servers testable.

### Testing

17. **New code ships with tests.** Unit tests for pure logic, integration tests for anything crossing a module boundary, agent eval fixtures for agent behavior changes.
18. **Mock LLMs, mock network, never mock SQLite.** Tests use a real `better-sqlite3` against an in-memory or temp-file DB. Details: `docs/07-delivery.md §1`.
19. **If you change a prompt, add or update an eval fixture.** Silent prompt changes are the most expensive bugs in this project.

---

## Common tasks

Step-by-step patterns for the most frequent kinds of change. Each task lists the docs you should load before starting.

### Add a new MCP tool to an existing internal server

**Load:** `docs/01-foundations.md`, `docs/02-agent-runtime.md`

1. Open the server package (e.g., `packages/mcp-atlas-db`).
2. Define Zod schemas for the tool's arguments and return value in `src/tools/{tool-name}.schemas.ts`.
3. Implement the tool in `src/tools/{tool-name}.ts` as a pure function that takes dependencies and returns `{ ok, data } | { ok: false, error }`. Never throw.
4. Register the tool in the server's `createServer()` with a clear description, the Zod schemas, and side-effect disclosure ("this writes to the database" or "this makes a network request").
5. Write unit tests in `src/tools/{tool-name}.test.ts`. Test happy path, validation failures, and at least one error path.
6. If the tool is used by an existing agent, update that agent's tool allowlist in `packages/agents`.
7. Run `pnpm typecheck && pnpm test`.

**Tool design checklist** (full version: `docs/02-agent-runtime.md §7`):

- Small and unambiguous — one responsibility per tool.
- Descriptive name (`get_profile`, not `profile`).
- Argument names match the domain (`listing_id`, not `params`).
- Typed, structured errors with machine-readable codes.
- Idempotency key where retries matter.
- Size limits on text responses.
- Side-effect disclosure in the description.

### Add a new agent

**Load:** `docs/01-foundations.md`, `docs/02-agent-runtime.md`, plus the relevant subsystem doc (`docs/05-...` or `docs/06-...`) if the agent belongs to one.

1. Create `packages/agents/src/{agent-name}/` with:
   - `prompt.ts` — the system prompt as a template string with placeholders.
   - `schemas.ts` — Zod schemas for the agent's input and expected output.
   - `definition.ts` — the agent definition object (name, prompt, tool allowlist, default model stage, fallback model, budgets, schemas).
   - `index.ts` — exports the definition.
2. Register the agent in `packages/agents/src/registry.ts`.
3. The prompt follows the six-section structure from `docs/02-agent-runtime.md §8`: Identity → Goal → Tools → Constraints → Output → Untrusted Content Stanza. Do not deviate.
4. Keep the tool allowlist **small** — 5–8 tools max. Weaker models get confused by large toolboxes.
5. Write at least three eval fixtures in `packages/eval/fixtures/{agent-name}/`: a happy-path case, an edge case, and a case that should fail gracefully. Include `expected.yaml` with deterministic assertions and LLM-as-judge assertions for content quality.
6. Run `pnpm eval -- --suite {agent-name}` and verify the suite passes against the reference model.
7. Update the agents table in `docs/08-reference.md §1` if this is a new primary agent.

### Add a database migration

**Load:** `docs/01-foundations.md`, `docs/03-persistence.md`

1. Modify the Drizzle schema in `packages/db/src/schema/{table}.ts`.
2. Run `pnpm db:generate` — this produces a new SQL migration file in `packages/db/migrations/`.
3. Inspect the generated SQL. Migrations must be **forward-only** and **idempotent** where possible. Never write a down migration.
4. If the change is destructive (rename, drop, type change), split it across multiple releases: add new column → backfill → switch reads → switch writes → drop old in a later release. Details: `docs/03-persistence.md §2`.
5. Test the migration on a copy of a populated dev DB: `pnpm db:migrate` with a backup ready.
6. Add a test that verifies the post-migration schema and data integrity.
7. **Never delete user data in a migration.** If a feature is removed, stop writing to its tables and leave them in place.

### Add an IPC channel

**Load:** `docs/01-foundations.md`, `docs/04-app-shell.md`

1. Define input and output Zod schemas in `packages/schemas/src/ipc/{namespace}.ts`.
2. Add the channel name to the IPC channel registry. Name it `namespace.verb` (e.g., `runs.kill`, `profile.import`).
3. Implement the handler in `apps/desktop/main/src/ipc/{namespace}.ts`. Wrap logic in try/catch; convert errors to structured `AtlasError` responses.
4. Expose the method in the preload script (`apps/desktop/preload/src/api/{namespace}.ts`) via `contextBridge`.
5. Use the channel from the renderer via a TanStack Query hook in `apps/desktop/renderer/src/hooks/{namespace}.ts`. Cache keys follow `[namespace, verb, ...args]`.
6. Write an integration test that calls the handler directly with valid and invalid payloads.

### Add a UI screen

**Load:** `docs/01-foundations.md`, `docs/04-app-shell.md`, plus the subsystem doc for whatever the screen is about.

1. Create a new route file under `apps/desktop/renderer/src/routes/`. TanStack Router picks it up via file-based routing.
2. Build the screen with shadcn/ui components only. Never introduce a new component library.
3. Use TanStack Query for anything coming from the main process. Use Zustand only for UI-local cross-component state.
4. Accessibility is required: keyboard focus on all interactive elements, visible focus rings, ARIA roles on custom widgets, WCAG AA contrast, alt text on images, keyboard-navigable without a mouse. shadcn/ui's Radix primitives give you most of this for free — don't break it.
5. URL state (filters, sort, selected item) goes in TanStack Router search params, not component state. This makes views bookmarkable.
6. Add the route to the sidebar navigation if it should be top-level.

### Add a scraper adapter

**Load:** `docs/01-foundations.md`, `docs/05-subsystems-discovery-evaluation-generation.md`

1. Create `packages/scrapers/src/{platform}/` with `list.ts`, `fetch.ts`, `canonicalize.ts`, and `adapter.ts` exporting the uniform interface.
2. Implement against the platform's public API where possible. See `docs/05-subsystems-discovery-evaluation-generation.md §2` for known platform endpoints.
3. Save HTML fixtures in `packages/scrapers/src/{platform}/__fixtures__/` for tests.
4. Write unit tests that parse the fixtures and verify the expected shape.
5. Register the adapter in `packages/scrapers/src/registry.ts` so the scheduler can dispatch to it.
6. Update the `sources` table schema if the adapter needs new config fields.

### Touching the Application Agent or approval flow

**Load:** `docs/01-foundations.md`, `docs/02-agent-runtime.md` (carefully — especially §11 and §12), `docs/06-subsystems-application-stories-negotiation.md`

This is the highest-stakes part of the codebase. Mistakes are user-visible and potentially embarrassing.

1. Read `docs/02-agent-runtime.md §11` (approval flow) end to end before writing any code.
2. Read `docs/02-agent-runtime.md §12` (prompt injection defense) for the threat model.
3. Read `docs/06-subsystems-application-stories-negotiation.md §1` for the Application Agent's specific design.
4. **If your task involves bypassing or relaxing any safety check, stop and ask.** Do not "improve" the approval flow without explicit approval.
5. Add eval fixtures specifically targeting the safety properties: "agent never calls submit without approval," "agent honors the kill switch," "agent terminates cleanly on unexpected page."

### Add a PDF template

**Load:** `docs/01-foundations.md`, `docs/07-delivery.md`, `docs/05-subsystems-discovery-evaluation-generation.md §4`

1. Create `packages/pdf-templates/{template-id}/` with `template.html`, `styles.css`, `fonts/`, and `manifest.json`.
2. The template is Mustache; **no embedded logic.** All computation happens in the generator agent.
3. Define the expected context schema in `manifest.json` (Zod-compatible structure).
4. Bundle fonts as woff2 in the template's `fonts/` directory.
5. Test rendering with a fixture context: `pnpm test:integration -- pdf-templates`.
6. Add a preview image to the template directory for the Settings picker.

---

## Testing expectations

Full strategy in `docs/07-delivery.md §1`. Quick rules:

- **Unit tests** for pure functions and schemas — target >80% coverage on `shared`, `schemas`, `db`, and tool implementations.
- **Integration tests** for module-boundary code (MCP servers, scrapers, IPC handlers, the harness loop).
- **Agent eval tests** for agent behavior. Mandatory for prompt or agent definition changes.
- **E2E tests** with Playwright Test for renderer flows. Use a mock Model Router.
- **Never test against real LLM providers in CI.** Always mock. The eval runner is the one exception — it runs against pinned models and is invoked manually or on release branches.

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
- [ ] Cross-references in docs you touched are still accurate

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
- **Never invent a new internal MCP server without checking `docs/02-agent-runtime.md §6`.** The seven servers there are the complete set for v1.
- **Never make the renderer a Node process ("just temporarily, for testing").** It is never a Node process. Not even once.
- **Never use React class components, Redux, or MobX.** The stack is function components + TanStack Query + Zustand.
- **Never add a new top-level dependency without justifying it.** Every new npm package is a maintenance and security burden. Prefer writing 50 lines over adding a 200-KB dependency.
- **Never change a migration file after it's been committed.** Write a new migration that fixes the problem.
- **Never load all eight technical docs at once "to be safe."** Use the lookup table in `docs/00-index.md` and load only what the task needs.

---

## When to stop and ask

Do not guess on any of these. Surface a question instead.

- The task requires adding architecture not described in the technical docs.
- The task requires changing a core invariant from the "Non-negotiable rules" section above.
- The task touches the Application Agent, submission tools, or the approval flow — these are high-stakes and mistakes are user-visible.
- The task requires a new MCP server, a new agent, or a new provider adapter.
- The task involves a third-party API not currently integrated.
- The task asks you to store something sensitive (credentials, tokens, PII) and you're not sure how.
- The task requires relaxing a safety rule "just this once."
- The product plan and a technical doc disagree on the right approach.
- Two technical docs disagree with each other.
- You find a bug in a core component (harness, IPC, DB) while working on something else.
- The existing tests don't cover the area you're modifying and you can't tell what correct behavior should be.
- You're not sure which docs to load for the task.

A question is always cheaper than a rollback.

---

## Style and code quality

- **Small files.** 300 lines is a smell, 500 lines is a bug. Refactor before you can't.
- **Pure functions where possible.** Side effects live at clearly-marked boundaries (IPC handlers, MCP tool bodies, DB writes, PDF renders).
- **Comments explain _why_, not _what_.** If the code is unclear, rewrite it instead of commenting it.
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

## Glossary (quick reference)

Full glossary in `docs/08-reference.md §6`. Top hits:

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

If anything in this file or the technical docs is unclear, surface it as a question in your response instead of guessing. Guessing on Atlas is expensive.
