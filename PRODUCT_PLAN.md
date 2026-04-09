# Project Atlas — Agentic Job Application Command Center

> A local-first, open-source desktop app where AI agents continuously discover jobs matching your profile, reason about fit, tailor your CV and cover letter per listing, and — with your approval — apply on your behalf. Agents use a library of MCP tools to act autonomously; deterministic code is the tool library, not the orchestrator.

---

## 1. Vision & Principles

**Vision.** Replace the manual job-hunt spreadsheet + Google Docs + 40 browser tabs workflow with a command center where AI agents work *for you* in the background and hand you a ranked pipeline of opportunities each morning.

**Core principles.**

1. **Local-first.** Everything runs on the user's machine. No cloud, no accounts, no telemetry. The user's CV, browsing history, and API keys never leave the device.
2. **Agentic, not scripted.** The LLM is the orchestrator. Deterministic code is a library of MCP tools the agent autonomously composes. When requirements change or a portal looks weird, the agent adapts; it doesn't break.
3. **Everything is an MCP tool.** Uniform interface across external (Playwright) and internal (DB, profile, filesystem, user-approval) capabilities. One tool protocol to rule them all.
4. **Bring your own model.** Model-agnostic. Users plug in Claude, OpenAI, OpenRouter, or Ollama and pay their own inference costs. The harness is resilient to weaker models.
5. **Reasoning over matching.** Fit is judged by agents reading the JD and the user's profile, not by keyword overlap.
6. **Tiered cost control.** Cheap models triage; expensive models deep-dive; budget ceilings are enforced by the harness, not prompts.
7. **Human-in-the-loop by default, YOLO by choice.** The default flow always requires explicit user approval before any irreversible action. YOLO mode is a scoped, per-batch opt-in.
8. **Honesty guardrail.** CV tailoring reorders and re-emphasizes; it never fabricates experience, titles, dates, or metrics. A separate verifier agent enforces this.
9. **Auditability.** Every agent action is captured in a structured trace: goal, reasoning summaries, tool calls with inputs/outputs, costs, durations. Nothing is a black box.
10. **Beautiful and accessible.** Non-technical users should enjoy opening the app. Accessibility is table stakes, not a phase 5 feature.
11. **Single source of truth.** One SQLite database holds the canonical state. Everything else is derived and reproducible.

---

## 2. Target User

A white-collar job seeker — engineer, designer, PM, marketer, operator, analyst — willing to install a desktop app and bring their own API key. Single user per install. The UI must be as approachable as a consumer app; the agent machinery is hidden behind clean views and clear approval prompts.

---

## 3. Core Concepts (Domain Model)

- **Profile.** The user's canonical self-description stored as YAML (parsed from whatever format they uploaded). Master CV, skills, preferences, constraints, salary expectations, geographic/visa situation, scoring weights.
- **Source.** A configured place to discover jobs from — a company career page, an ATS board query, an RSS feed, a search query.
- **Listing.** A single job posting pulled from a source. Deduplicated, with a canonical URL and archived raw snapshot.
- **Evaluation.** An agent-produced structured reasoning about a listing against the profile: the 6 blocks, the 10-dimension scorecard, the letter grade, and the recommendation.
- **Application.** A listing the user committed to applying for. Holds tailored CV, tailored cover letter, generated answers to application questions, submission status, and the full agent trace.
- **Story.** A STAR+R narrative in the user's Story Bank, tagged with themes and used for interview prep and cover letter hooks.
- **Run.** A single agent invocation: a goal, a scoped toolbox, a budget, a trace, and a result. Runs are the atomic unit of agent work and the atomic unit of the audit log.
- **Trace.** The structured record of everything that happened during a run: model calls, tool calls, inputs, outputs, reasoning summaries, costs, timings. The trace is the unit of debugging.
- **Agent.** A named configuration: a system prompt + a tool allowlist + a default model + budget ceilings. Agents are defined declaratively and instantiated by the harness per run.

---

## 4. The 10-Dimension Scoring System

Each dimension is rated 0–10 by the evaluator agent with a one-sentence justification. Dimensions are multiplied by user-configurable weights and summed into a letter grade.

| # | Dimension | What it measures | Default weight |
|---|---|---|---|
| 1 | **Role–Skill Alignment** | How well the user's demonstrated skills and experience match what the JD actually requires | 18% |
| 2 | **Seniority Fit** | Level match — avoids both undershoot and overshoot | 10% |
| 3 | **Compensation** | Expected total comp vs. the user's target band and market data for the role/location | 15% |
| 4 | **Growth Trajectory** | How much this role would expand the user's skills, surface area, or career capital | 12% |
| 5 | **Company Health** | Funding stage, runway, recent layoffs, public financials, Glassdoor/Blind signal | 8% |
| 6 | **Mission & Domain Fit** | Does the user actually care about the product, industry, or problem space | 10% |
| 7 | **Work Model Fit** | Remote / hybrid / onsite alignment with the user's preference and constraints | 8% |
| 8 | **Geography & Visa** | Location, relocation requirements, visa sponsorship, time-zone overlap | 7% |
| 9 | **Team & Leadership Signal** | Quality signals about the hiring manager, founders, team size, engineering culture | 6% |
| 10 | **Application Friction** | Effort required relative to expected value | 6% |

**Letter grade mapping** (default, user-editable):

- **A** ≥ 8.5 — apply immediately, invest in personalization
- **B** 7.0–8.4 — apply, standard effort
- **C** 5.5–6.9 — apply only if pipeline is light, or archive
- **D** 4.0–5.4 — archive, maybe revisit
- **F** < 4.0 — auto-archive, don't notify

Each evaluation includes a **"why this grade"** paragraph and **"what would move this up a letter"** hint.

---

## 5. The 6-Block Evaluation

Every listing that passes triage gets a deep evaluation with these six blocks, produced by the Evaluation Agent using its toolbox.

### Block 1 — Role Summary
A no-BS TL;DR of what the job actually is, stripped of buzzwords. Day-to-day work, reporting line, team shape, what's mentioned vs. conspicuously absent. 3–5 bullets max.

### Block 2 — CV Match
Reasoned fit analysis. For each of the top 5 JD requirements, the agent points to specific evidence in the profile (or flags absence). Ends with "gaps and how to frame them."

### Block 3 — Level Strategy
Which seniority to position for, what to emphasize, what to de-emphasize, expected interview loop at that level.

### Block 4 — Comp Research
Market data for the role, location, and company stage. Expected base, equity, total comp range. Leverage points. Company comp philosophy if discoverable. Flags vague listings. This block is where the agent uses `web.search` most heavily.

### Block 5 — Personalization
Specific hooks for the cover letter and interview: recent company news, founder background, product launches, engineering blog posts, mutual connections, relevant Story Bank entries.

### Block 6 — Interview Prep (STAR+R)
Likely interview questions at each loop stage, mapped to specific stories. Gaps trigger an interactive Story Bank session.

---

## 6. Feature List

Original features plus additions I think are necessary. Additions are marked **[+]**.

### Discovery & Ingestion

| Feature | Description |
|---|---|
| **Portal Scanner** | 45+ pre-configured companies + custom queries across Ashby, Greenhouse, Lever, Wellfound, Workable, SmartRecruiters |
| **Generic-site discovery agent [+]** | When a source is a career page with no known adapter, an agent crawls it using browser tools |
| **RSS Ingestion** | Subscribe to job newsletters and aggregator feeds |
| **LinkedIn (experimental)** | Best-effort scraping; isolated module so it can be disabled without affecting anything else |
| **Per-source scheduling [+]** | User configures frequency per source |
| **Per-source dedup config [+]** | URL match, title+company, or semantic similarity |
| **Raw snapshot archive [+]** | Every scraped listing's HTML is archived so re-evaluation is reproducible |
| **Source health dashboard [+]** | Which sources are broken, returning zero results, or rate-limited |

### Evaluation

| Feature | Description |
|---|---|
| **Tiered evaluation** | Cheap triage agent → expensive deep-dive agent on promising matches |
| **6-Block deep evaluation** | Produced by the Evaluation Agent with web + DB tools |
| **10-Dimension A–F scoring** | Weighted, user-configurable |
| **Batch processing** | Parallel evaluation via worker pool; configurable concurrency and cost ceiling |
| **Re-evaluation [+]** | Re-run when the profile changes so old listings get updated scores |
| **Evaluation diff [+]** | See how a re-evaluation changed from the previous one |
| **Cost tracking [+]** | Per-run and per-month spend, broken down by agent, model, and stage |

### Profile, CV & Cover Letter Generation

| Feature | Description |
|---|---|
| **Universal profile parser** | Accepts PDF, DOCX, YAML, JSON, Markdown, freeform text; produces canonical YAML |
| **Canonical YAML schema** | Single source of truth for the user's self-description; versioned |
| **ATS-optimized PDF generation** | Multiple templates; Space Grotesk + DM Sans default |
| **Keyword injection (honest)** | Reorders bullets and emphasizes existing experience. Never fabricates. |
| **Template library [+]** | Classic, modern, minimalist, technical, design-forward |
| **Cover letter generation** | Personalized per listing using Block 5 hooks and Story Bank content |
| **Honesty Verifier Agent [+]** | Separate agent pass checks every claim against canonical profile; flags unsupported content |
| **Diff view [+]** | See exactly what changed between master CV and tailored CV |

### Application Submission

| Feature | Description |
|---|---|
| **Auto-Pipeline** | Paste a URL → evaluation + PDF + cover letter + tracker entry |
| **HITL mode (default)** | Application Agent fills the form, calls `user.request_approval` with a screenshot, waits |
| **YOLO mode** | Agent fills and submits without waiting; scoped per-batch, audited, kill-switchable |
| **AI-answered questions** | Open-ended form fields answered using profile and Story Bank |
| **CAPTCHA / MFA handoff [+]** | Agent detects and calls `user.request_approval` with context |
| **Rate limiting [+]** | Throttles per-portal submissions |
| **Kill switch [+]** | Single hotkey halts all agent runs at their next harness check |
| **Dry-run mode [+]** | Fills forms in a visible browser but the `browser.submit` tool is disabled |

### Story Bank & Interview Prep

| Feature | Description |
|---|---|
| **Interactive intake** | First-run: a Story Bank Agent interviews the user conversationally to extract 5–10 master stories |
| **Passive accumulation** | New stories surfaced from CV and past evaluations |
| **On-demand interactive mode** | When evaluation detects a gap, triggers an interview session |
| **Theme tagging** | Leadership, conflict, ambiguity, failure, cross-functional… |
| **Story rehearsal mode [+]** | Practice drill with likely questions and relevant stories |

### Negotiation

| Feature | Description |
|---|---|
| **Offer entity [+]** | Offers are first-class: base, bonus, equity, sign-on, start date, deadline, counter-offers |
| **Fully personalized scripts** | Generated against the specific offer, leverage, competing offers, context |
| **Counter-offer simulator [+]** | What-if modeling |
| **Deadline tracker [+]** | Surfaces offers approaching decision deadlines |

### Tracking & Pipeline Integrity

| Feature | Description |
|---|---|
| **Single SQLite source of truth** | All state in one DB file |
| **Status state machine [+]** | Discovered → Evaluated → Shortlisted → Applied → Screening → Interviewing → Offer → Closed |
| **Automated dedup and merge** | Same job from 3 sources becomes one listing |
| **Health checks** | Periodic integrity audits |
| **Agent trace log [+]** | Append-only structured log of every agent run |
| **Backup & export [+]** | One-click zip of DB + files + traces |
| **Rejection analysis [+]** | An agent analyzes rejection patterns and suggests profile adjustments |

### Interface

| Feature | Description |
|---|---|
| **Desktop app** | Cross-platform, macOS primary |
| **Dashboard** | Browse, filter, sort, bulk-act on the pipeline |
| **Listing detail view** | Full evaluation, tailored CV preview, cover letter preview, apply button |
| **Approval queue [+]** | Central inbox for HITL approval requests from running agents, with screenshots and context |
| **Profile editor** | Friendly form UI over canonical YAML; non-technical users never touch YAML directly |
| **Settings** | API keys, agent model routing, budget ceilings, notification preferences |
| **Desktop notifications** | New A-grade match, approval needed, status change, rejection, offer |
| **Email digest** | Daily summary |
| **Trace viewer [+]** | Searchable, filterable view of agent runs with full step-by-step drilldown |
| **Cost dashboard [+]** | Per-agent, per-model, per-day spend with budget bars |

### Safety, Privacy, Secrets

| Feature | Description |
|---|---|
| **Encrypted secrets store** | API keys and portal credentials in OS keychain |
| **Credential scoping** | Portal credentials only decrypted in-memory during the specific submission needing them |
| **No telemetry** | Zero outbound traffic except to user-configured LLM providers and scrape targets |
| **Honesty Verifier Agent** | Dedicated pass that checks generated content against profile |
| **Prompt-injection defense [+]** | All scraped content wrapped in untrusted-content markers; irreversible actions gated behind `user.request_approval` which cannot be satisfied by the model |

---

## 7. Architecture — Agentic

The architecture has three layers: the app shell (UI + IPC), the agent runtime (harness + MCP tool library), and persistence (SQLite + files + secrets).

```
┌─────────────────────────────────────────────────────────────┐
│                Electron Renderer (React + TS)               │
│  Dashboard · Profile · Approval Queue · Trace Viewer · …    │
└───────────────┬─────────────────────────────────────────────┘
                │ typed IPC (contextBridge + Zod)
┌───────────────┴─────────────────────────────────────────────┐
│                Electron Main (Node + TS)                    │
│                                                             │
│  ┌───────────────────────────────────────────────────────┐  │
│  │                  Agent Harness                        │  │
│  │  budget · trace · scoping · approval · kill-switch    │  │
│  │  retries · untrusted-content wrapping · eval hooks    │  │
│  └───────────────────────────────────────────────────────┘  │
│                          │                                  │
│  ┌───────────────────────┴───────────────────────────────┐  │
│  │          Vercel AI SDK  —  generateText + tools       │  │
│  │     uniform loop across Claude/OpenAI/OR/Ollama       │  │
│  └───────────────────────────────────────────────────────┘  │
│                          │                                  │
│  ┌───────────────────────┴───────────────────────────────┐  │
│  │                   MCP Client Layer                    │  │
│  └───────────────────────────────────────────────────────┘  │
│         │          │          │         │         │         │
│    ┌────┴───┐ ┌────┴────┐┌────┴────┐┌───┴────┐┌──┴────┐     │
│    │Playwright│ │ atlas ││ atlas  ││ atlas ││ atlas │      │
│    │   MCP   │ │  db   ││profile ││  fs   ││  web  │       │
│    │(external│ │  MCP  ││  MCP   ││  MCP  ││  MCP  │       │
│    │  npm)  │ │(internal││(internal││(internal││(internal│   │
│    └────────┘ └────────┘└────────┘└────────┘└───────┘      │
│                                                             │
│                    ┌─────────────┐                          │
│                    │atlas user   │  ← approval/interaction  │
│                    │  MCP        │                          │
│                    │(internal)   │                          │
│                    └─────────────┘                          │
│                                                             │
│  ┌───────────────────────────────────────────────────────┐  │
│  │     Worker Pool (utilityProcess)  ·  p-limit queues   │  │
│  └───────────────────────────────────────────────────────┘  │
└───────────────┬─────────────────────────────────────────────┘
                │
┌───────────────┴─────────────────────────────────────────────┐
│  SQLite (better-sqlite3 + Drizzle)  ·  Files (PDFs, HTML)   │
│  Secrets (keytar → OS keychain)                             │
└─────────────────────────────────────────────────────────────┘
```

### The Agent Harness

The harness is ~300–500 lines of TypeScript you own. It wraps the Vercel AI SDK's `generateText` loop and enforces everything the SDK doesn't care about but you deeply do:

1. **Budget enforcement.** Before each loop iteration, the harness checks cumulative cost against the run's ceiling. Over budget → clean termination with a "budget exceeded" result.
2. **Iteration cap.** Hard ceiling on loop turns, independent of the SDK's `maxSteps`.
3. **Wall-time cap.** Agents killed cleanly if they run too long.
4. **Trace capture.** Every model call and tool call logged as a structured event: parent run id, step index, tool name, input, output, tokens, cost, duration, error (if any). Written to SQLite `traces` table.
5. **Tool scoping.** Agents are instantiated with a named tool allowlist. The harness filters MCP-advertised tools to only the allowed set before passing them to the SDK. The evaluation agent literally cannot see `browser.click`.
6. **Untrusted-content wrapping.** Any text from scraped pages, JDs, or forms is wrapped in `<untrusted_content>…</untrusted_content>` markers. System prompts explicitly say content between markers is untrusted data, not instructions.
7. **Approval tool enforcement.** `user.request_approval()` is special: its result can't be faked because it blocks on real user IPC. The harness enforces that submission tools require a successful approval in the same run (in HITL mode).
8. **Kill switch.** A flag checked between iterations. UI kill button sets it. All running agents die cleanly at their next check.
9. **Retry with schema feedback.** When a tool call's arguments fail Zod validation, the harness returns a structured error to the model so it can retry with corrected arguments. Capped at N retries per tool call.
10. **Eval hooks.** Each run can be tagged with an eval suite id so golden-set runs can be replayed and compared.

### Agent Definitions

Agents are defined declaratively in code as configuration objects:

```ts
{
  name: "evaluation.deep",
  systemPrompt: "...",
  tools: [
    "atlas-db.get_profile",
    "atlas-db.write_evaluation",
    "atlas-web.search",
    "atlas-web.fetch",
    "playwright.navigate",
    "playwright.get_text",
  ],
  defaultModel: "claude-sonnet-4-5",
  fallbackModel: "openrouter/anthropic/claude-3.5-sonnet",
  budgets: { maxSteps: 20, maxCostUsd: 0.50, maxWallMs: 180_000 },
  evalSuite: "evaluation-v1",
}
```

### The Agents

| Agent | Purpose | Tool allowlist (abbreviated) | Notes |
|---|---|---|---|
| **Profile Parser Agent** | Converts uploaded CV into canonical YAML | `atlas-fs.read`, `atlas-profile.validate_schema` | Single-shot, not really a loop; ~1–2 iterations |
| **Discovery Agent** | Crawls known ATS platforms and generic career pages | `playwright.*`, `atlas-db.write_listing`, `atlas-web.fetch` | Scoped per-source |
| **Triage Agent** | Cheap, fast grade-only pass on new listings | `atlas-db.get_profile`, `atlas-db.read_listing` | Cheapest model tier |
| **Evaluation Agent** | 6-block deep evaluation on promising listings | `atlas-db.*`, `atlas-web.*`, `playwright.navigate`, `playwright.get_text` | Expensive model tier |
| **CV Tailor Agent** | Generates tailored CV from master profile + JD | `atlas-profile.read`, `atlas-db.read_evaluation`, `atlas-fs.write_template_context` | Structured output |
| **Cover Letter Agent** | Generates tailored cover letter | Same as CV Tailor + `atlas-stories.query` | |
| **Honesty Verifier Agent** | Checks generated CV/cover letter against profile | `atlas-profile.read`, `atlas-db.read_generated_asset` | Different model from generator when possible |
| **Application Agent** | Fills and (with approval) submits applications | `playwright.*`, `atlas-profile.read`, `atlas-user.request_approval`, `atlas-stories.query` | The primary agentic surface; no `browser.submit` without approval in HITL mode |
| **Story Bank Interview Agent** | Conversational intake and gap-filling | `atlas-user.ask`, `atlas-db.write_story` | Interactive; long-running |
| **Negotiation Agent** | Personalized script generation | `atlas-db.read_offer`, `atlas-web.search`, `atlas-user.ask` | |
| **Rejection Analyst Agent** | Analyzes rejection patterns | `atlas-db.query_rejections`, `atlas-profile.read` | Periodic |

### The MCP Tool Library

Everything is an MCP tool. Internal MCP servers are in-process modules that speak MCP over stdio; the agent doesn't know or care which are external.

**External MCP servers.**
- **Playwright MCP** (`@playwright/mcp`) — browser automation. Used by Discovery Agent and Application Agent.

**Internal MCP servers (all in the Atlas repo).**
- **atlas-db** — typed CRUD over the Drizzle-backed SQLite: `get_profile`, `read_listing`, `write_evaluation`, `query_applications`, `write_trace_event`, …
- **atlas-profile** — structured access to the canonical profile: `read`, `query_skills`, `query_experience`, `validate_schema`, `query_stories`.
- **atlas-fs** — sandboxed file I/O scoped to Atlas's own directories: `read`, `write`, `list`, `render_pdf` (HTML → PDF via Puppeteer).
- **atlas-web** — web access that's separate from browser automation: `search`, `fetch`, `extract_markdown`. Rate-limited and caching.
- **atlas-user** — the bridge to the human: `request_approval(screenshot, description, options)`, `ask(question, options)`, `notify(message, level)`. These tools call over IPC to the renderer, which surfaces UI and blocks until the user acts. Irreversible actions are gated on these.
- **atlas-stories** — dedicated access to the Story Bank: `query(theme, question)`, `write`, `list`.
- **atlas-cost** — `get_budget_remaining(run_id)`, `estimate(prompt_tokens, output_tokens, model)`. Agents can introspect their own budget if needed.

Each internal MCP server is a ~100–300 line module exposing a small, well-named, Zod-schemed tool surface. Tool design follows a few rules:

- **Small and unambiguous.** `click_button(selector)` beats `interact_with_page(action, target, value)`.
- **No mega-tools.** Each tool does one thing.
- **Typed errors.** Tools return `{ ok: true, data }` or `{ ok: false, error: "human-readable reason" }`, never throw across the MCP boundary.
- **Idempotent where possible.** Reads are always idempotent; writes include an idempotency key when the agent needs retry safety.
- **Side-effect disclosure.** Tool descriptions explicitly say "this writes to the database" or "this makes a network request" so the model can reason about reversibility.

### Why the Vercel AI SDK loop + thin harness + MCP

The case, briefly:
- **Uniform provider support.** AI SDK handles Claude, OpenAI, OpenRouter, Ollama tool-calling quirks. For a BYO-model product this is irreplaceable.
- **Native MCP client.** `experimental_createMCPClient` is the cleanest path to "everything is MCP."
- **Ownership of the loop.** Budget, approval, scoping, tracing, and prompt-injection defense are enforced in code you own, not in a framework's opinions.
- **Resilient to weaker models.** Ollama and cheap OpenRouter models have uneven tool-call quality. Schema-validated retries, small toolboxes, few-shot examples, and clear error feedback make this workable. Heavier frameworks' abstractions sometimes get in the way of this kind of defensive work.
- **No framework bet.** The code is yours.

### Concurrency & Workers

Heavy work runs in Electron `utilityProcess` workers for true parallelism and isolation. Concurrency is capped at every stage by `p-limit` — Node will happily fire 500 concurrent LLM calls and melt your wallet; this is an architectural concern from day one, not a bolt-on.

### Resilience for Weaker Models (Ollama, cheap OpenRouter)

Hard-won principles baked into the harness and agent configs:

1. **Small toolboxes.** 5–8 tools per agent, not 30. Weaker models get confused by large surfaces.
2. **Few-shot examples.** Each tool's description includes an example call when targeting weaker model tiers.
3. **Schema-feedback retries.** Invalid arguments return a structured error to the model, capped at 3 retries.
4. **Clear termination conditions.** Agents always have a "done" tool or a structured-output mode so they can signal completion unambiguously.
5. **Model fallback chains.** Each agent has a primary model and a fallback; the harness promotes to fallback after repeated failures.
6. **Model pinning for reproducibility.** Eval suites pin exact model versions so regressions are visible.

---

## 8. Data Model (High-Level Sketch)

```
profiles               (canonical profile, YAML blob + parsed fields)
preferences            (scoring weights, grade thresholds, defaults)
sources                (career pages, ATS queries, RSS feeds)
listings               (unique jobs)
listing_sources        (M:N — which sources saw this listing)
listing_snapshots      (archived raw HTML + metadata)
evaluations            (one per listing per profile version)
scorecards             (10-dimension breakdown per evaluation)
applications           (listings committed to applying)
application_assets     (tailored CV PDFs, cover letters, answers)
offers                 (linked to applications)
stories                (STAR+R Story Bank)
story_links            (stories referenced by evaluations / cover letters)
runs                   (agent runs: goal, agent_name, model, budgets, result)
trace_events           (per-step events inside runs: tool calls, model calls)
approvals              (HITL approval requests and responses)
costs                  (per-call cost tracking, joinable to runs)
```

The `runs` + `trace_events` + `approvals` triplet is what makes the agentic layer debuggable. Every agent run produces a browsable, replayable trace.

---

## 9. Tech Stack

| Layer | Choice | Notes |
|---|---|---|
| **App shell** | Electron (latest stable) | Cross-platform, mature, best-in-class Playwright integration |
| **Language** | TypeScript 5.x (strict mode) | End-to-end, main + renderer |
| **Frontend framework** | React 18 | Required for shadcn/ui |
| **Build tool** | Vite via `electron-vite` | Fast HMR for both main and renderer |
| **Styling** | Tailwind CSS | Utility-first, pairs with shadcn/ui |
| **Component library** | shadcn/ui (Radix primitives) | Accessible, customizable, you own the code |
| **Icons** | Lucide | |
| **Typography** | Space Grotesk + DM Sans | Shared between UI and generated CVs |
| **Routing** | TanStack Router | Type-safe |
| **State** | Zustand (UI) + TanStack Query (server state) | Minimal |
| **IPC** | `contextBridge` with typed channels via shared Zod schemas | Type-safe end-to-end |
| **Database** | SQLite via `better-sqlite3` | Synchronous, fast, local-first friendly |
| **ORM / migrations** | Drizzle ORM | Type-safe, SQL-first |
| **Agent runtime** | Vercel AI SDK (`ai` + provider packages) + thin owned harness | Uniform across providers, MCP-native |
| **MCP client** | `experimental_createMCPClient` from the AI SDK | |
| **MCP server SDK** | `@modelcontextprotocol/sdk` (TypeScript) | For internal MCP servers |
| **External MCP** | `@playwright/mcp` | Browser automation |
| **Browser automation** | Playwright (Node-native, via Playwright MCP) | |
| **Static HTML parsing** | Cheerio | For non-JS-heavy targets (used inside tool implementations) |
| **RSS** | `rss-parser` | |
| **PDF generation** | Puppeteer rendering HTML/CSS → PDF | Pixel-perfect typography |
| **Scheduling** | `node-cron` + SQLite-backed run queue | |
| **Concurrency control** | `p-limit`, `p-queue` | Per-stage caps; non-negotiable from day one |
| **Workers** | Electron `utilityProcess` | True process isolation |
| **Secrets** | `keytar` → macOS Keychain / Windows Credential Manager / Linux Secret Service | |
| **Validation** | Zod | Schemas for IPC, tool I/O, profile, LLM structured outputs |
| **YAML** | `yaml` package | Canonical profile parsing |
| **DOCX parsing** | `mammoth` | Profile import |
| **PDF parsing** | `pdf-parse` + LLM vision fallback for scanned PDFs | Profile import |
| **Logging** | `pino` with file transport | Structured JSON logs |
| **Testing** | Vitest for unit, Playwright Test for e2e, custom agent eval runner | |
| **Linting** | ESLint + Prettier + typescript-eslint | |
| **Packaging** | `electron-builder` | `.dmg`, `.msi`, `.AppImage` |
| **Auto-update** | `electron-updater` against GitHub Releases | Free for open source |

---

## 10. Agent Evaluation — A New Discipline

In a fully agentic system, unit tests don't cover enough. Agents are stochastic; the same input may take different paths. You need agent evals, which are a different practice from unit tests.

**The setup.**
- **Golden fixtures.** Curated inputs (real JD URLs, real profile YAMLs, real rejection corpora) with hand-written expected outcomes at the *behavior* level: "agent produces a valid evaluation," "agent's final grade is within 0.5 of the reference," "agent never calls `browser.submit` without approval," "agent's tailored CV passes the honesty verifier."
- **Eval runner.** A harness mode that runs an agent against a fixture with a pinned model, captures the full trace, and grades it. Grading is a mix of deterministic checks (schema valid, tools in allowlist, approval called before submit) and LLM-as-judge checks (is the evaluation actually good).
- **CI integration.** Eval suites run on every PR against a cheap model set; full suites run manually before releases.
- **Regression detection.** When a new provider version ships or a prompt changes, evals catch drift.
- **Replay.** Any production trace can be saved as a new eval fixture. When a real run goes badly, "add as eval case" is a single click.

This is its own body of work and warrants a dedicated track in the roadmap.

---

## 11. Phased Roadmap

Explicit phases because the surface area is enormous and shipping a working Phase 1 beats planning a perfect Phase 5.

### Phase 0 — Foundation (weeks 1–3)

*Goal: the agent harness works end-to-end against a real MCP tool and a real model, with trace, budget, and approval enforcement.*

Concrete task list:

1. **Project scaffolding.** `electron-vite` with React + TypeScript, strict tsconfig, ESLint + Prettier, Vitest.
2. **Typed IPC layer.** `contextBridge` + Zod schemas. Shared schema module. Round-trip `ping/pong`.
3. **SQLite + Drizzle.** Schema v1: `profiles`, `preferences`, `runs`, `trace_events`, `approvals`, `costs`, `audit_log`. First migration committed. DB lives in Electron `userData`.
4. **Canonical profile YAML schema** defined in Zod. TypeScript types inferred from it.
5. **Secrets store.** `keytar` integration. Settings UI with "test connection" per provider.
6. **Vercel AI SDK wired up** with adapters for Anthropic, OpenAI, OpenRouter, Ollama. A hello-world `generateText` call logs cost to the `costs` table.
7. **Agent Harness v1.** The core loop: budget enforcement, iteration cap, wall-time cap, trace capture to `trace_events`, kill switch, schema-feedback retries, untrusted-content wrapping. ~300 lines plus tests.
8. **First internal MCP server: `atlas-db`.** Built with `@modelcontextprotocol/sdk`. Exposes `get_profile`, `write_trace_event`. In-process, stdio transport.
9. **First internal MCP server: `atlas-user`.** Exposes `request_approval` and `ask`. Tools bridge over IPC to a dedicated Approval Queue UI screen that blocks the agent until the user responds.
10. **First agent: a trivial "echo-profile" agent** that uses `atlas-db.get_profile`, echoes part of it, calls `atlas-user.request_approval` to confirm, and terminates. Runs end-to-end through the harness. Trace is viewable in a basic Trace Viewer screen.
11. **Universal profile parser.** PDF (`pdf-parse` + LLM vision fallback), DOCX (`mammoth`), YAML, JSON, Markdown, freeform text. Implemented as the Profile Parser Agent — uses `atlas-fs.read` (new, small atlas-fs MCP server) and produces canonical YAML validated against the Zod schema.
12. **App shell UI.** Sidebar nav. Screens: Profile (import + preview), Settings (keys + model routing + budgets), Approval Queue, Trace Viewer. Tailwind + shadcn/ui, Space Grotesk + DM Sans loaded.
13. **Packaging sanity check.** `electron-builder` produces a working `.dmg`.

**Exit criteria:** you import a PDF CV, it's parsed into canonical YAML by the Profile Parser Agent, you see the full trace of that run in the Trace Viewer including every tool call and its cost, you can kill a running agent from the UI, and you can package the app as a `.dmg`.

### Phase 1 — Evaluate-from-URL MVP (weeks 4–7)

*Goal: paste a URL, an agent produces the full treatment.*

- **`atlas-web` MCP server** with `search` and `fetch`.
- **`atlas-fs` MCP server** expanded with `render_pdf`.
- **Playwright MCP** wired up as an external MCP server.
- **Evaluation Agent.** System prompt, tool allowlist, budget config. Produces the 6-block evaluation and 10-dimension scorecard as structured output.
- **CV Tailor Agent.** Structured output populates an HTML/CSS template; rendered to PDF via Puppeteer.
- **Cover Letter Agent.** Same pipeline.
- **Honesty Verifier Agent.** Separate model call that diffs generated content against profile YAML and flags unsupported claims.
- **Listing and Evaluation UI views.** Listing detail page shows the full 6-block evaluation, scorecard, grade, tailored CV preview, cover letter preview, and the trace of the agents that produced them.
- **Agent eval runner v1** with 10–20 golden fixtures for the Evaluation Agent.

**Exit criteria:** paste any JD URL; within 2 minutes and under $0.50 of inference, you see a graded 6-block evaluation, a tailored CV PDF, and a cover letter, with every agent's trace browsable.

### Phase 2 — Discovery Engine (weeks 8–11)

*Goal: the pipeline fills itself.*

- **Playwright MCP integration matures.** Discovery Agent's toolbox is refined.
- **Known-platform adapters as fast paths** — Greenhouse, Ashby, Lever, Wellfound have deterministic discovery functions (faster and cheaper than agent crawling); the agent is the fallback for generic career pages and when adapters break.
- **45+ pre-configured company sources** seeded at install.
- **RSS ingestion** via `rss-parser`.
- **Scheduler** with per-source frequency; SQLite-backed run queue.
- **Triage Agent** for cheap grade-only passes on new listings.
- **Tiered evaluation pipeline** — Triage Agent → Evaluation Agent on promising matches only.
- **Dedup and merge engine.**
- **Source health dashboard.**
- **Dashboard view** with filter/sort/bulk actions.
- **Desktop notifications** for new A-grade matches.
- **Cost dashboard.**

**Exit criteria:** set it up on Monday, open it on Friday, find a ranked pipeline of fresh listings you didn't have to look for, with cost under a user-set weekly budget.

### Phase 3 — Agentic Application Engine (weeks 12–16)

*Goal: the bot does the tedious part, you do the thinking part. This is the biggest agentic surface in the whole app and the phase gets extra time because mistakes here are user-visible and potentially embarrassing.*

- **Application Agent.** System prompt, toolbox, budgets. Uses Playwright MCP for browser control, `atlas-profile` for field values, `atlas-stories` for open-ended questions, and `atlas-user.request_approval` for every irreversible action.
- **Approval Queue UX** is the star of this phase: a dedicated, delightful UI for the user to review what the agent wants to do, see a screenshot, and approve or correct.
- **HITL mode** is the default; `browser.submit` is not in the agent's toolbox without a successful approval in the same run.
- **YOLO mode** is a scoped, per-batch opt-in that temporarily adds `browser.submit` to the allowlist. Always audited. Global kill switch.
- **CAPTCHA / MFA detection.** The agent detects and calls `user.request_approval` with context.
- **Rate limiting per portal.**
- **Dry-run mode.** The `browser.submit` tool is replaced with a no-op that logs "would have submitted."
- **Encrypted portal credential store.**
- **Agent evals for Application Agent.** Golden fixtures of real portals in staging; mostly behavioral checks ("agent called request_approval before submit," "agent never bypassed a CAPTCHA").

**Exit criteria:** shortlist 10 jobs, hit "apply all in HITL", approve them one by one from the Approval Queue without touching the browser yourself. Zero surprise submissions.

### Phase 4 — Story Bank, Negotiation, YOLO, Rejection Analyst (weeks 17–20)

*Goal: the features that make it a command center, not just an applicator.*

- **Story Bank Interview Agent.** First-run conversational intake. On-demand gap-filling sessions.
- **Passive story extraction** from CV and past evaluations.
- **Story-aware cover letters and Block 6 interview prep.**
- **Offer entity** in the DB.
- **Negotiation Agent.** Fully personalized scripts per offer with web research.
- **Counter-offer simulator.**
- **YOLO mode** hardened and shipped.
- **Rejection Analyst Agent.** Periodic run that analyzes rejection patterns and surfaces insights.

**Exit criteria:** you've done at least one real interview loop using only Block 6 prep, and one real negotiation using the generated scripts.

### Phase 5 — Polish & Hardening (weeks 21+)

*Goal: the stuff that makes it actually good to live in.*

- **LinkedIn adapter** (experimental, best-effort, isolated).
- **Multiple CV templates.**
- **Email digest** (SMTP or local HTML fallback).
- **Backup & export.**
- **Pipeline integrity health checks.**
- **Re-evaluation + diff view.**
- **Trace Viewer v2** with search, filter, replay.
- **Story rehearsal mode.**
- **Auto-update** via `electron-updater`.
- **Agent eval suites expanded** and running in CI against cheap models.
- **Open-source launch** — docs, contribution guide, demo video.

---

## 12. Risks & Mitigations

| Risk | Mitigation |
|---|---|
| **Agent cost runaway** | Per-run budget ceilings enforced in harness; global monthly cap; tiered models; `p-limit` concurrency caps; cost dashboard with alerts |
| **Agent infinite loops** | Harness enforces max iterations and wall-time caps independent of SDK |
| **Prompt injection from scraped content** | All untrusted content wrapped in clear markers; irreversible actions gated on `atlas-user.request_approval`, which cannot be satisfied by the model alone; system prompt explicitly says instructions in untrusted blocks must be ignored |
| **Agent drifts between model versions** | Eval suites pin models; regressions caught before release |
| **Tool misuse** | Per-agent tool allowlists enforced by harness, not by prompt; evaluation agent literally cannot see `browser.click` |
| **Weak models (Ollama, cheap OpenRouter) fail to use tools well** | Small toolboxes, few-shot examples, schema-validated retries, model fallback chains, honest documentation of which models are "primary" vs. "compatible" |
| **LLM hallucinates experience in tailored CV** | Honesty Verifier Agent runs as a separate pass with a different model; diff view; user acknowledgment required for any flagged insertion |
| **User forgets YOLO mode is on and 30 applications go out** | YOLO is scoped per-batch, requires explicit re-arming; audit log; global kill switch; desktop notification whenever YOLO is active |
| **ATS platforms detect and block automation** | Realistic timing, rate limits, persistent cookies per portal, fall back to HITL when challenged, keep LinkedIn isolated |
| **Portal credentials leak** | `keytar` / OS keychain only, decrypted in-memory for the duration of one submission, never logged, never in traces |
| **Scraper adapters break silently** | Source health dashboard, zero-result alerts, snapshot archive, agent fallback for broken known-platform adapters |
| **Electron security footguns (XSS → RCE)** | `contextIsolation: true`, `nodeIntegration: false`, `sandbox: true`, strict CSP, no remote content in renderer |
| **Trace log grows unboundedly** | Retention policy with configurable window; archive older traces to disk |
| **Non-deterministic bugs are hard to reproduce** | Full trace replay from `trace_events`; "save as eval fixture" on any run |
| **Solo-dev scope creep** | Strict phase gates; Phase 1 is usable on its own |
| **ToS violations** | Personal tool framing; conservative defaults; LinkedIn and YOLO opt-in |

---

## 13. Open Questions to Revisit Later

1. **Windows + Linux parity.** macOS is primary; per-release testing on others?
2. **Email digest delivery.** SMTP or local HTML fallback?
3. **Interview scheduling.** Out of scope for v1 but tempting.
4. **Mobile companion** for read/approve. Explicitly out of scope for now.
5. **Telemetry for the open-source release.** Opt-in crash reports only or nothing at all?
6. **"Primary supported model" tier.** Should the docs explicitly say "Claude Sonnet is the reference model; Ollama is best-effort" to set expectations honestly?
7. **Trace sharing for bug reports.** If a user wants to report an agent gone wrong, how do they share a trace without leaking their profile? Scrubbing pipeline?
