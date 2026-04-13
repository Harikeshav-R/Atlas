# Atlas Technical Documentation — Index

> This is the entry point to Atlas's technical documentation. The full design has been split into focused documents so that an agent working on a specific area only needs to load the relevant pieces. **Read this file first, then load only the documents the task requires.**

The product-level "what and why" lives in `product-plan.md` at the project root. The engineering "how" lives in the documents listed below. The rules, conventions, and prohibitions you must follow on every task live in `CLAUDE.md` at the project root.

---

## Document map

| # | File | Scope | When to load |
|---|---|---|---|
| 00 | `docs/00-index.md` | This index | Every session |
| 01 | `docs/01-foundations.md` | Repo layout, runtime topology, cross-cutting conventions (IDs, time, errors, logging, validation) | Every task |
| 02 | `docs/02-agent-runtime.md` | Agent harness, Model Router, MCP tool library, tool design, prompt engineering, budgets, traces, approval flow, prompt injection defense, agent evaluation framework | Any task touching agents, prompts, MCP servers, the harness, or tool implementations |
| 03 | `docs/03-persistence.md` | Database schema, migrations, file system layout, secrets management | Any task touching the database, storage, or secrets |
| 04 | `docs/04-app-shell.md` | Electron security hardening, IPC layer, worker pool, renderer architecture | Any task touching Electron config, IPC channels, workers, or the renderer UI |
| 05 | `docs/05-subsystems-discovery-evaluation-generation.md` | Canonical profile schema, discovery subsystem, evaluation subsystem, generation subsystem (CV + cover letter) | Tasks on profile parsing, scrapers, evaluation agents, or CV/cover letter generation |
| 06 | `docs/06-subsystems-application-stories-negotiation.md` | Application engine, story bank, negotiation, scheduler/run queue, desktop notifications, email digest | Tasks on auto-apply, the application agent, the story bank, negotiation, scheduling, or notifications |
| 07 | `docs/07-delivery.md` | Testing strategy, build/packaging/release, observability/debugging, development workflow, PDF rendering pipeline, first-run UX, operational runbook | Tasks on tests, CI, builds, releases, PDF templates, onboarding, or debugging |
| 08 | `docs/08-reference.md` | Quick-reference tables (agents, status state machine, defaults, limits), out-of-scope list, glossary | Reach for when you need a lookup but not deep context |

---

## Task → required reading lookup

Use this table to decide which documents to load for the task you're given. **Always load `01-foundations.md`** in addition to whatever else the task requires; it contains conventions every other doc assumes.

| Task | Required reading |
|---|---|
| Add an MCP tool to an existing internal server | 01, 02 |
| Create a new internal MCP server | 01, 02, 03 |
| Add a new agent | 01, 02 (+ the relevant subsystem doc 05 or 06 if the agent belongs to one) |
| Modify the agent harness | 01, 02 |
| Modify the Model Router | 01, 02 |
| Change a system prompt | 01, 02 (+ the relevant subsystem doc) |
| Add or modify a database table | 01, 03 |
| Write a Drizzle migration | 01, 03 |
| Add an IPC channel | 01, 04 |
| Build or modify a UI screen | 01, 04 (+ the subsystem doc for whatever the screen is about) |
| Modify Electron security or main-process config | 01, 04 |
| Touch the worker pool | 01, 04, 02 |
| Change the canonical profile schema | 01, 03, 05 |
| Add or modify a scraper adapter | 01, 05 |
| Work on the Discovery, Triage, or Evaluation Agent | 01, 02, 05 |
| Work on CV Tailor, Cover Letter, or Honesty Verifier Agent | 01, 02, 05, 07 (for the PDF pipeline) |
| Work on the Application Agent | 01, 02, 06 (high stakes — read carefully) |
| Touch the approval flow or any gated tool | 01, 02, 06 |
| Work on the Story Bank or Story Bank Interview Agent | 01, 02, 06 |
| Work on Negotiation or the Negotiation Agent | 01, 02, 06 |
| Modify the scheduler or run queue | 01, 06 |
| Work on desktop notifications or email digest | 01, 06 |
| Add or modify a PDF template | 01, 07 |
| Modify the build, packaging, or release pipeline | 01, 07 |
| Modify the test setup or CI | 01, 07 |
| Work on the trace viewer | 01, 02, 04 |
| Work on the cost dashboard | 01, 03, 04 |
| Work on the first-run experience | 01, 04, 05, 07 |
| Add a new dependency | 01 (justify in the PR description) |
| Look up an agent's tool allowlist or default budget | 08 |
| Look up the application status state machine | 08 |
| Look up a term you don't recognize | 08 |

If your task isn't in this table and you're not sure what to load, **load 01 and 02 and stop to ask**. Loading the wrong docs is cheap; building against the wrong assumptions is expensive.

---

## Reading order for new contributors

If you're loading this for the first time and want a complete mental model before doing any work, read the documents in numerical order. Plan to spend a couple of hours; it's worth it. After that, use the lookup table above for individual tasks.

---

## Cross-references

Documents reference each other using paths like `docs/02-agent-runtime.md §11` (read as "section 11 of the agent runtime doc"). Section numbers are stable within a document; if you find a stale cross-reference, fix it in the same PR.
