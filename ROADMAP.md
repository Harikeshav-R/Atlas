# Project Atlas — Execution Roadmap

> Sequential, step-by-step plan for building Atlas from empty repo to v1.0 release. Each step has a clear deliverable and a definition of done. Work through them in order — later steps assume earlier ones are complete.
>
> **Solo-dev, spare-time pace assumption:** ~10 hours/week. Total estimate ~21 calendar weeks of active work (6–9 months of elapsed time). Adjust based on your actual pace; the *order* matters more than the *dates*.
>
> **Companion docs:** `product-plan.md` for the what/why, `CLAUDE.md` for coding rules, `docs/00-index.md` for technical reference.

---

## How to use this document

- Work steps in order. Do not skip ahead, even if a later step looks more interesting — earlier steps are load-bearing for later ones.
- Each step lists: **what you're building**, **why it's next**, **definition of done**, and **relevant docs**.
- When a step is done, commit, push, check off the box, and move to the next one.
- If you hit a blocker, note it and move laterally within the current phase rather than across phases.
- **Do not start Phase N+1 until Phase N's "phase gate" is met.** The gates are there to catch "I'll fix it later" debt before it compounds.

---

## Phase 0 — Foundation (target: 3 weeks)

**Goal:** a working Electron app that runs an echo-profile agent end-to-end. No real features yet — just proof that every architectural layer is wired up and the agent loop actually loops.

**Why this first:** every later phase assumes the harness works, the DB works, MCP servers work, and the renderer can talk to main. Proving this on a trivial agent is 10× cheaper than debugging it under the pressure of a real feature.

### Step 0.1 — Decide on the project name and license

- [ ] Check `npm`, GitHub, and USPTO for "Atlas" conflicts. If heavily conflicted, pick an alternative.
- [ ] Create `LICENSE` file (AGPL v3 full text).
- [ ] Create `CONTRIBUTING.md` with DCO sign-off instructions.
- [ ] Create a minimal `README.md` with name, one-liner, license.
- [ ] `git init`, push to GitHub as a public repo.

**Done when:** repo exists publicly with license and README.

### Step 0.2 — Scaffold the monorepo

- [ ] `pnpm init` at root, set `"packageManager": "pnpm@9.x"`.
- [ ] Create `pnpm-workspace.yaml` listing `apps/*` and `packages/*`.
- [ ] Install Turborepo, create `turbo.json` with a basic `build`/`test`/`lint` pipeline.
- [ ] Create `tsconfig.base.json` at root with strict mode, `noUncheckedIndexedAccess`, `exactOptionalPropertyTypes`.
- [ ] Create empty package dirs per `docs/01-foundations.md §1`.
- [ ] Set up ESLint, Prettier, `lint-staged`, `husky` pre-commit.
- [ ] Drop in `CLAUDE.md`, `product-plan.md`, and `docs/` from the outputs.

**Done when:** `pnpm install && pnpm typecheck && pnpm lint` all succeed on an empty repo.

### Step 0.3 — Build `@atlas/shared` and `@atlas/schemas`

- [ ] `@atlas/shared`: `newId(prefix)`, `now()` (mockable), `AtlasError`, `tryCatch`, `pino` logger with scrubbing middleware, `wrapUntrusted` helper.
- [ ] `@atlas/schemas`: start with IPC base types, a stub canonical profile schema, tool I/O base types.
- [ ] Unit tests for each utility.

**Done when:** both packages publish-ready locally and tested.

### Step 0.4 — Build `@atlas/db` with Phase 0 tables

- [ ] Install `better-sqlite3` and Drizzle.
- [ ] Define schemas for `profiles`, `runs`, `trace_events`, `approvals`, `costs`, `model_pricing`, `audit_log`. (Other tables come in later phases.)
- [ ] Generate the initial migration.
- [ ] Write a `createDb(path)` helper and query helpers for the above tables.
- [ ] Unit tests against an in-memory DB.

**Done when:** migrations apply cleanly, helpers work, tests pass.

### Step 0.5 — Build the harness skeleton with fakes

- [ ] `@atlas/harness`: the `run(agentDef, input, options)` function per `docs/02-agent-runtime.md §1`.
- [ ] Implement: budget enforcement, iteration cap, wall-time cap, tool scoping, kill switch, trace capture, schema-feedback retries.
- [ ] Do NOT integrate real MCP or real models yet — use fakes that return scripted responses.
- [ ] Unit tests covering each enforcement point.

**Done when:** the harness runs a fake agent with a fake model and fake tools, enforces every limit correctly, and produces a valid trace. This is the most important test in the project — get it right.

### Step 0.6 — Build `mcp-atlas-db` and `mcp-atlas-user`

- [ ] Use `@modelcontextprotocol/sdk` to build both servers as stdio-transport MCP servers.
- [ ] `atlas-db`: minimal tools — `get_profile`, `write_trace_event`.
- [ ] `atlas-user`: `request_approval` (blocking on a promise bound to an approval ID), `ask`, `notify`.
- [ ] Integration test: harness → MCP client → server → DB write, end to end.

**Done when:** the harness can call these servers and the DB reflects the result.

### Step 0.7 — Build `@atlas/model-router` with Anthropic only

- [ ] Install `ai` SDK and the Anthropic adapter.
- [ ] Implement stage-based routing with a hard-coded mapping for Phase 0.
- [ ] Cost tracking via token counts → `model_pricing` lookup.
- [ ] No fallback chains yet (Phase 2).

**Done when:** `generateText` works through the router and costs are recorded.

### Step 0.8 — Build the echo-profile agent

- [ ] Agent definition in `packages/agents/src/echo-profile/`.
- [ ] Prompt: "Read the profile via `atlas-db.get_profile` and echo back the user's name."
- [ ] Tool allowlist: `atlas-db.get_profile` only.
- [ ] Seed a fake profile in the DB.
- [ ] Run the agent via the harness end-to-end. Verify trace, cost, result.

**Done when:** `pnpm run agent echo-profile` prints the name and writes a complete trace.

### Step 0.9 — Build the Electron shell

- [ ] `apps/desktop` with `electron-vite` setup.
- [ ] Main process: hardened per `docs/04-app-shell.md §1`. Loads DB, spawns MCP servers, registers harness.
- [ ] Preload script exposing a tiny IPC surface (`runs.start`, `runs.get`).
- [ ] Renderer: React + Tailwind + TanStack Router with two screens — Profile viewer (read-only) and Trace viewer.
- [ ] Wire "Run echo-profile agent" button → IPC → harness → trace renders in Trace viewer.

**Done when:** you click a button in the app window, the agent runs, and you see the full trace update live.

### Step 0.10 — Build the Profile Parser Agent

- [ ] Add `mcp-atlas-fs` and `mcp-atlas-profile` MCP servers.
- [ ] Implement the Profile Parser Agent per `docs/05-...md §1`.
- [ ] Add a "Import Profile" screen that accepts a PDF upload.
- [ ] Run the parser → produce canonical YAML → persist to DB.

**Done when:** you can import a real PDF CV and see the canonical YAML in the DB.

### Step 0.11 — Package as a `.dmg`

- [ ] `electron-builder` config for macOS DMG (unsigned is fine for now).
- [ ] `pnpm build` produces a working DMG.
- [ ] Install the DMG on your own machine and run the Phase 0 flow.

**Done when:** the app installs from a DMG and does everything above.

### 🚪 Phase 0 Gate

Before Phase 1: harness tests pass, the kill switch works mid-run, traces are complete, costs are recorded, and the app is installable. If any of these are shaky, fix them now.

---

## Phase 1 — Evaluate-from-URL MVP (target: 4 weeks)

**Goal:** paste a job URL → get a full evaluation with grade, scorecard, and the 6 blocks. No discovery, no applications yet. This is the first feature real users would find useful.

### Step 1.1 — Add remaining DB tables

- [ ] `listings`, `listing_snapshots`, `evaluations`, `scorecards`, `preferences`. Migrations forward-only.

### Step 1.2 — Build `mcp-atlas-web`

- [ ] `search` (via DuckDuckGo HTML or user's Brave API key) and `fetch` (with markdown extraction).
- [ ] Per-domain rate limiting, response size caps, caching.

### Step 1.3 — Build one scraper adapter end-to-end

- [ ] Pick Greenhouse (simplest public API). Implement `list`, `fetch`, `canonicalize` per `docs/05-...md §2`.
- [ ] Dedup via URL canonicalization against `listings` table.
- [ ] Test against saved HTML fixtures.

### Step 1.4 — Build the Triage Agent

- [ ] Small, cheap, single-call agent returning a go/no-go with a numeric score.
- [ ] Eval fixtures with expected grades.

### Step 1.5 — Build the Evaluation Agent

- [ ] Full 6-block output, validated by Zod.
- [ ] Tools: `atlas-db.*`, `atlas-profile.*`, `atlas-web.*`.
- [ ] Eval fixtures covering strong/weak/ambiguous matches.

### Step 1.6 — Renderer: Listing detail screen

- [ ] Paste-URL flow → fetch → triage → evaluate.
- [ ] Show the 6 blocks and scorecard. Grade badge. Re-evaluate button.

### Step 1.7 — Settings screen for providers, models, budgets

- [ ] API key input → keytar. Stage-to-model mapping. Monthly budget.

### Step 1.8 — Onboarding for Phase 1

- [ ] Minimum viable first-run: import profile → add API key → paste URL.

### 🚪 Phase 1 Gate

Run a real URL evaluation end to end. Cost matches expectations. Trace is clean. Share with 2–3 friends for feedback.

---

## Phase 2 — Discovery (target: 4 weeks)

**Goal:** Atlas discovers listings autonomously from configured sources and builds a pipeline.

### Step 2.1 — Add `sources`, `listing_sources` tables; the scheduler

- [ ] Scheduler per `docs/06-...md §4`. Persistent cron.

### Step 2.2 — More scraper adapters

- [ ] Ashby, Lever, Wellfound. Each with fixtures and tests.

### Step 2.3 — RSS ingestion

- [ ] Newsletter mode with a small extraction agent for multi-job posts.

### Step 2.4 — Generic-site Discovery Agent

- [ ] Playwright-powered agentic path for career pages without adapters.
- [ ] External MCP: `@playwright/mcp` integration.

### Step 2.5 — Dashboard screen

- [ ] Pipeline view, filters, sort, bulk actions, grade badges.

### Step 2.6 — Sources management screen

- [ ] CRUD UI, source health, consecutive-failure detection.

### Step 2.7 — Worker pool

- [ ] `utilityProcess`-based workers per `docs/04-...md §3`. Parallel evaluations. No DB from workers.

### Step 2.8 — Model Router fallback chains

- [ ] Primary + fallback per stage.

### 🚪 Phase 2 Gate

Discover 50+ listings from 5+ configured sources in a week. Pipeline feels real. No runaway costs.

---

## Phase 3 — Application Agent (target: 5 weeks)

**Goal:** Atlas tailors documents and submits applications with HITL approval. Highest-stakes phase.

### Step 3.1 — Add `applications`, `application_assets` tables

### Step 3.2 — PDF pipeline

- [ ] Puppeteer-based renderer, one default template per `docs/07-...md §5`.

### Step 3.3 — CV Tailor Agent + Cover Letter Agent + Honesty Verifier

- [ ] Strict rules: reorder and reword, never fabricate. Verifier catches violations.
- [ ] Eval fixtures including fabrication attempts.

### Step 3.4 — Approval flow UI

- [ ] Approval Queue screen. Screenshot, summary, approve/deny/modify. Desktop notifications.

### Step 3.5 — Application Agent

- [ ] Greenhouse adapter hints first, then Ashby and Lever.
- [ ] Submit-gate wrapper in the harness enforcing approval scopes.
- [ ] Dry-run mode fully functional.

### Step 3.6 — Safety evals

- [ ] "Never submits without approval." "Honors kill switch." "Terminates on unexpected page." "Resists prompt injection in JD content."

### 🚪 Phase 3 Gate

Complete 10 real applications in dry-run mode. Then complete 3 real applications with HITL. Zero unapproved submissions. If any safety eval fails, phase is not done.

---

## Phase 4 — Stories, Negotiation, YOLO (target: 4 weeks)

### Step 4.1 — Story Bank

- [ ] `stories`, `story_links` tables. `mcp-atlas-stories` server.
- [ ] Story Bank Interview Agent with pause/resume.
- [ ] Wire into Cover Letter Agent.

### Step 4.2 — Negotiation

- [ ] `offers` table. Structured entry form. Negotiation Agent. Counter-offer simulator.

### Step 4.3 — Rejection Analyst

- [ ] Monthly auto-run. Pattern detection across rejected applications.

### Step 4.4 — YOLO mode

- [ ] Per-batch scope, auto-approve with visible 10s delay, auto-disable after batch. Kill switch still works.

### Step 4.5 — Email digest

- [ ] Opt-in, SMTP via keytar, or HTML-to-browser fallback.

### 🚪 Phase 4 Gate

Story Bank has 8+ stories. A negotiation script is used in a real conversation (yours or a friend's). YOLO runs a 5-app batch cleanly.

---

## Phase 5 — Polish, eval, release (target: 2 weeks)

### Step 5.1 — Agent eval suite expansion

- [ ] Every agent has ≥5 fixtures. Suites run in CI on release branches.

### Step 5.2 — Accessibility audit

- [ ] Keyboard-only walkthrough. Screen-reader pass. Fix what you find.

### Step 5.3 — Cost dashboard polish

- [ ] Per-agent, per-model breakdowns. Projected month-end.

### Step 5.4 — Bug-report flow with scrubbing

### Step 5.5 — macOS code signing and notarization

- [ ] Enroll in Apple Developer Program. Automate signed builds in CI.

### Step 5.6 — Auto-update via `electron-updater`

### Step 5.7 — Documentation pass

- [ ] User-facing docs: install, first-run, troubleshooting.

### Step 5.8 — Closed beta with 5–10 users

- [ ] Collect traces (scrubbed) and feedback. Fix top 10 issues.

### Step 5.9 — v1.0 release

- [ ] Public release. Hacker News/Reddit/etc.

---

## What to do *after* v1.0

Not a phase — just principles for the long haul.

- **Issue triage cadence:** weekly. Don't let the queue become a graveyard.
- **Model refresh:** monthly, re-run eval suites against current provider versions.
- **Scraper adapter maintenance:** whichever fails most often gets rewritten first.
- **Feature requests:** collect, but don't commit. A small, opinionated tool wins over a feature-accretion product.
- **The out-of-scope list** (`docs/08-reference.md §5`) stays out of scope until you have strong evidence otherwise.

---

## If you fall behind

Completely normal on a spare-time project. In priority order:

1. **Never skip Phase 0.** Hacking features onto a broken harness wastes 10× more time than Phase 0 took.
2. **Phase 1 alone is a useful product.** If life happens and you only ever ship Phase 1, you still have a "paste-URL evaluator" people would use. Protect that MVP milestone.
3. **Phase 3 is the real commitment.** If you get to the start of Phase 3 and lose energy, consider shipping Phases 1–2 as v0.5 and taking a break.
4. **Cut Phase 4 before cutting Phase 3 quality.** A safe HITL-only Atlas is shippable; an unsafe YOLO Atlas is a lawsuit.
5. **Don't cut evals.** Ever. They're what separates "it works for me" from "it works for users."

Good luck. Ship the thing.
