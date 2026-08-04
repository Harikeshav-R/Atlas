# Atlas — Project Design Document

> **Atlas** is a local-first, terminal-native (TUI) job-application co-pilot for software
> engineers. It discovers matching jobs, tailors a one-page resume and cover letter per
> posting from a master resume, drafts application-form answers, and tracks every
> application through to offer — all driven by AI that runs either through a locally
> installed coding CLI (Claude Code, OpenAI Codex, Google Antigravity) or through a
> hosted API (Amazon Bedrock, OpenRouter, Anthropic, …).

- **Status:** Design / pre-implementation
- **Language:** Python 3.11+ · managed with **uv**
- **Interface:** Interactive TUI (Textual) + scriptable CLI (Typer)
- **Data:** Local SQLite via **SQLModel**; secrets in the OS keychain
- **Distribution:** `uv tool install atlas` / `pipx install atlas`
- **Last updated:** 2026-08-01

---

## 1. Vision & Summary

Job searching is a high-volume, repetitive, emotionally draining pipeline: find postings,
read each one, rewrite the resume to match, write a cover letter, answer the same essay
questions again, submit, then track dozens of applications across states and deadlines.

Atlas automates the parts a machine is good at and keeps the human in control of the parts
that matter. It runs quietly in the background finding roles that fit the user's stated
preferences, and when the user opens the TUI it presents a ranked queue of opportunities.
For any job — one Atlas found, or one the user pastes a link to — Atlas reads the posting
and produces a tailored one-page resume, a custom cover letter, and draft answers to the
posting's application questions, all derived from a single **master resume** the user
maintains. Atlas never submits on the user's behalf; it prepares everything and the user
applies manually, then Atlas tracks the application through OA → interview → offer and
manages calendar events and deadlines.

**Core design principles**

1. **Local-first & private.** All user data lives on the user's machine. Nothing is sent
   anywhere except to the AI backend the user explicitly chose.
2. **Bring-your-own-AI.** The AI layer is a pluggable adapter. The default path drives a
   coding CLI already installed on the machine; an API path is a first-class alternative.
3. **Human-in-the-loop for anything outward-facing.** Atlas prepares; the user decides,
   edits, and submits.
4. **Truth-anchored tailoring.** Tailored resumes are built from real content in the
   master resume. Fabrication controls are configurable (see §11).
5. **Explainable.** Every match score, every tailoring decision, comes with a rationale
   the user can read.

---

## 2. Goals & Non-Goals

### 2.1 Goals

- Onboard a user through a friendly Q&A that captures job-search preferences.
- Maintain a Markdown **master resume** as the single source of truth for the user's
  experience.
- Support **multiple search profiles** (e.g. "Backend Engineer" and "ML Engineer") that
  share one master resume but differ in preferences, match criteria, and tailoring
  emphasis.
- Discover jobs in the background via (a) a **company watchlist** (per-company ATS boards)
  and (b) **aggregator keyword searches**.
- Let the user paste any **job posting URL** and have Atlas scrape + parse it.
- **Score every candidate posting** for fit with an AI-generated rationale, presenting a
  ranked queue.
- Produce a **tailored one-page resume** (PDF) per application via an HTML/CSS → PDF
  pipeline.
- Produce a **custom cover letter** per application.
- Draft answers to **application-form questions** the user pastes in.
- **Track application status** (Saved → Applied → OA → Interview → Offer/Rejected/…) with
  optional **email inbox scanning** to auto-advance status.
- Manage **calendar events** (OAs, interviews, deadlines) via CalDAV.
- Run as a **local daemon** with a separate **TUI client**.
- Work through **coding-CLI adapters by default**, with **API adapters** as an option.

### 2.2 Non-Goals (explicitly out of scope)

- **No auto-submission** of applications. Ever, in any phase.
- **No credential storage for job boards** or logging into LinkedIn/Indeed on the user's
  behalf.
- Not a general ATS/CRM for recruiters — it is single-user, candidate-side.
- Not a resume *writing from scratch* tool — the user provides the master resume content.
- No mobile/web UI in the roadmap covered here (terminal-native only).
- No mass/spray applying — Atlas is deliberately per-posting and quality-oriented.

---

## 3. Personas & Primary User Journeys

### 3.1 Persona

**"Sam", a software engineer** actively job-hunting. Comfortable in a terminal, has a
coding CLI installed and authenticated, keeps a detailed resume, applies to 5–30 roles a
week, and is losing track of deadlines and which resume version went where.

### 3.2 Journey A — First run / onboarding

1. `atlas init` launches the onboarding wizard (TUI).
2. Q&A captures preferences (roles, seniority, locations/remote, salary floor, fields,
   company size, culture, work authorization, must-haves/deal-breakers).
3. User points Atlas at their master resume Markdown file (or pastes it).
4. User picks an AI backend (auto-detected CLIs are listed; API option available).
5. Atlas validates the backend with a tiny test prompt, parses the master resume into
   structured sections, and creates the first search profile.

### 3.3 Journey B — Background discovery → review

1. `atlas daemon start` runs the poller. On a schedule it queries watchlist ATS boards
   and aggregator searches, dedupes, and AI-scores new postings.
2. Sam opens the TUI later; the **Discover** screen shows a ranked queue of new matches
   with scores and one-line rationales.
3. Sam opens a posting, reads the full parsed description and the fit rationale, and
   clicks **Tailor** to generate materials, or **Dismiss**.

### 3.4 Journey C — Paste a URL

1. Sam finds a job elsewhere and runs `atlas add <url>` (or pastes into the TUI).
2. Atlas scrapes and parses the posting, scores it, and offers to tailor.

### 3.5 Journey D — Tailor & apply

1. From a posting, Sam runs **Tailor**. Atlas produces: tailored resume (PDF preview),
   cover letter, and drafted answers to any pasted application questions.
2. Sam edits any of them inline, regenerates sections, and exports the final PDFs.
3. Sam applies manually on the company site, returns to Atlas, and marks it **Applied**.

### 3.6 Journey E — Track & schedule

1. An OA invite arrives. Either Sam updates status to **OA — due <date>**, or (if email
   scan is enabled) Atlas detects it and proposes the status change + a calendar event.
2. Atlas writes the event to the user's CalDAV calendar and sets reminders.
3. The TUI's **Pipeline** and **Calendar** views show upcoming deadlines and stage counts.

---

## 4. High-Level Architecture

```
┌──────────────────────────────────────────────────────────────────────┐
│                          User's machine                                │
│                                                                        │
│   ┌────────────────┐         IPC / shared DB        ┌───────────────┐  │
│   │   TUI client   │  ◄──────────────────────────►  │  atlas daemon │  │
│   │  (Textual)     │      (SQLite + local socket)   │  (scheduler)  │  │
│   └───────┬────────┘                                └──────┬────────┘  │
│           │                                                │           │
│           ▼                                                ▼           │
│   ┌────────────────────────────────────────────────────────────────┐  │
│   │                      Core service layer                         │  │
│   │  profiles · discovery · scraping · matching · tailoring ·       │  │
│   │  cover-letter · qa-drafting · rendering · tracking · calendar · │  │
│   │  email-scan                                                     │  │
│   └───────┬───────────────┬───────────────┬──────────────┬─────────┘  │
│           │               │               │              │            │
│           ▼               ▼               ▼              ▼            │
│   ┌────────────┐  ┌──────────────┐  ┌───────────┐  ┌──────────────┐   │
│   │ AI Provider│  │ Job Sources  │  │ Renderer  │  │ Integrations │   │
│   │  adapters  │  │  adapters    │  │ HTML→PDF  │  │ CalDAV/IMAP  │   │
│   └─────┬──────┘  └──────────────┘  └───────────┘  └──────────────┘   │
│         │                                                             │
│   ┌─────┴───────────────────────────────┐                            │
│   │ CLI adapters   │   API adapters      │                            │
│   │ claude/codex/  │  Bedrock/OpenRouter │                            │
│   │ antigravity    │  /Anthropic/…       │                            │
│   └────────────────┴─────────────────────┘                           │
│                                                                        │
│   ┌────────────────────────────────────────────────────────────────┐ │
│   │ Local storage: SQLite (data) · files (resumes/PDFs) · keyring   │ │
│   └────────────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────────────┘
```

### 4.1 Process model

- **Daemon (`atlas daemon`)**: long-running process. Owns the scheduler (APScheduler),
  runs discovery polls, AI scoring, and optional email scans, and writes results to
  SQLite. Exposes a small local IPC surface (Unix domain socket / named pipe) for the TUI
  to trigger on-demand actions and stream progress. Fires **native desktop notifications**
  (see §5.16) for new high-fit matches and upcoming deadlines even when the TUI is closed.
- **TUI client (`atlas` / `atlas tui`)**: the interactive app. Reads/writes the same
  SQLite DB, talks to the daemon over IPC when it needs to trigger work (e.g. "tailor this
  now"), and can run fully standalone if the daemon isn't running (foreground work still
  functions; only scheduled background discovery requires the daemon).
- **CLI subcommands**: thin scriptable entry points (`atlas add`, `atlas tailor`,
  `atlas status`, etc.) for automation and users who prefer flags over the TUI.

Concurrency safety: SQLite in WAL mode; the daemon is the single writer for
discovery/scoring rows, the TUI writes user-driven rows; short transactions; a lightweight
row-level "owned by" convention to avoid double work.

---

## 5. Component Specifications

### 5.1 AI Provider Abstraction (`atlas.ai`)

The keystone of the system. A single interface, many backends.

```python
class LLMResponse(BaseModel):
    text: str
    raw: dict | None          # backend-native payload for debugging
    usage: Usage | None       # tokens/cost when the backend reports it
    model: str
    backend: str

class LLMProvider(Protocol):
    name: str
    def is_available(self) -> bool: ...
    def complete(self, request: LLMRequest) -> LLMResponse: ...
    def stream(self, request: LLMRequest) -> Iterator[str]: ...

class LLMRequest(BaseModel):
    system: str | None
    prompt: str
    # Atlas asks for JSON when it needs structure; providers enforce/validate.
    response_schema: dict | None = None
    max_tokens: int | None = None
    temperature: float | None = None
    timeout_s: int = 120
```

**Backends** *(exact invocations verified against the three tools' headless docs — see
[Appendix A](#appendix-a--coding-cli-adapter-reference) for full command reference)*

| Backend | Type | Invocation (structured mode) | Structured output |
|---|---|---|---|
| **Claude Code** *(default CLI)* | CLI | `claude -p "<prompt>" --output-format json --json-schema '<schema>'` | JSON envelope; result in `structured_output`, text in `result`, cost in `total_cost_usd` |
| OpenAI Codex CLI | CLI | `codex exec --skip-git-repo-check --sandbox read-only --output-schema <file> "<prompt>"` | Final JSON on stdout conforming to schema (`--json` for JSONL event stream) |
| Google Antigravity CLI | CLI | `agy -p "<prompt>" --output-format json --json-schema '<schema>'` | JSON envelope; result in `structured_output`, text in `response`, `status`, `usage` |
| **OpenRouter** *(default API)* | API | via **LiteLLM** | JSON mode / structured outputs |
| Amazon Bedrock | API | via **LiteLLM** | Model id + region configurable |
| Anthropic API | API | via **LiteLLM** | Structured outputs |
| Google Gemini, DeepSeek, Groq, … | API | via **LiteLLM** | 100+ providers, one interface |
| Generic OpenAI-compatible / local (Ollama, LM Studio) | API | via **LiteLLM** | `base_url` + key |

> **API backends go through [LiteLLM](https://github.com/BerriAI/litellm) behind Atlas's own
> `LLMProvider` interface** (§5.1a) — one library covers OpenRouter, Bedrock, Anthropic,
> Gemini, DeepSeek, Groq, Ollama, and any OpenAI-compatible endpoint, so Atlas doesn't
> hand-roll a `boto3`/`httpx`/`anthropic` adapter per vendor. The coding-**CLI** backends
> (Claude Code / Codex / Antigravity) are **not** LiteLLM — they remain Atlas's own
> subprocess adapters (LiteLLM can't drive them). Keeping LiteLLM behind our interface means
> the API path stays swappable if we ever outgrow it.

**CLI adapter design (the hard part)**

Coding CLIs are built to edit repos, not to be text APIs — but usefully, **all three
selected CLIs expose a headless mode with `--output-format json` and a JSON-schema flag**,
so Atlas's structured-output contract (§5.1 / §7) maps cleanly onto every one of them. The
adapter strategy exploits that:

- **Unified structured path**: every AI task carries a Pydantic-derived JSON Schema. The
  adapter passes it to the CLI's schema flag and reads the parsed object back from the
  tool's structured field (`structured_output` for Claude Code & Antigravity; the
  schema-conformant final stdout message for Codex). This avoids fragile free-text
  scraping on the happy path.
- **`CliAdapter` base class** handles: building argv, running via `subprocess` with a
  timeout, feeding the prompt (arg or stdin), capturing stdout/stderr **separately** (all
  three send diagnostics to stderr and the answer/JSON to stdout), parsing the envelope,
  mapping status/usage, and normalizing errors. Each tool is a subclass encoding its exact
  flags, envelope shape, and quirks.
- **Neutralize agent behavior** — Atlas only wants text/JSON back, never file edits or
  shell commands:
  - *Claude Code*: run in a scratch working dir; pass **no** `--allowedTools` so nothing is
    auto-approved; the prompt/system-prompt instructs "respond directly, do not use tools."
  - *Codex*: `--sandbox read-only` blocks writes, and `--skip-git-repo-check` avoids
    Codex's hard requirement to run inside a git repo (or Atlas `git init`s the scratch
    dir). `--ephemeral` avoids persisting session rollout files.
  - *Antigravity*: shell commands are soft-denied by default in headless mode; run in a
    scratch workspace so its auto-allowed workspace file writes are harmless.
- **Isolation**: each CLI call runs in a per-call temp working directory with no repo
  context, so project `CLAUDE.md`/rules/hooks aren't picked up.
- **Capability probing** (`atlas doctor` + first setup): detect the binary (`--version`),
  run a tiny "reply OK as JSON against this schema" round-trip, and record support for JSON
  output, JSON schema, streaming, system-prompt injection, and model override. Cached and
  used to drive per-backend behavior and pick the best output mode.
- **Robust parsing & repair**: on the happy path, read the structured field. If a CLI
  returns malformed/empty structured output, fall back to extracting a delimiter-fenced
  JSON block from the text field, then run a bounded JSON-repair retry, then surface a
  clear error (and optionally fail over to the next backend).
- **Auth model** (differs per tool — surfaced in setup):
  - *Claude Code* uses the user's existing login/OAuth by default. (Its `--bare` mode is
    faster but **skips keychain/OAuth** and needs `ANTHROPIC_API_KEY`; Atlas offers `--bare`
    as an opt-in for API-key users and uses non-bare + isolated cwd otherwise.)
  - *Codex* reuses saved CLI auth, or takes `CODEX_API_KEY` per invocation.
  - *Antigravity* uses cached credentials — the user must authenticate once interactively
    first; a headless run with no auth exits with an "authentication required" error, which
    Atlas detects and reports with a fix hint.
- **Timeouts, status & cost**: Atlas sets generous per-call timeouts (Antigravity honors
  `--print-timeout`; Claude Code has print/background wait env vars), checks the `status`
  field where present (Antigravity's `SUCCESS/ERROR/…`), and records `usage`/`total_cost_usd`
  when the tool reports it. On timeout/SIGTERM the child process tree is terminated.
- **Failover**: on hard error, auth failure, or quota/rate-limit, try the next backend in
  the configured chain (e.g. Claude Code → OpenRouter).

**API adapter design (LiteLLM, behind our interface)**

A single `LiteLLMProvider` implements the `LLMProvider` interface for **all** API backends,
so adding a vendor is config, not code. Design (patterns validated by the reference project
Resume-Matcher, which uses LiteLLM in a very similar app — see §19):

- **One `litellm.Router`** (cached) fronts all API providers, configured with a
  `RetryPolicy`. **Transport retries live in the Router** (network/5xx/rate-limit backoff);
  callers must **not** re-retry transport — they only handle *content-quality* retries
  (bad JSON). Keeping these two retry layers separate avoids multiplicative retry storms.
- **Model capabilities come from a registry, not hardcoded** — whether a model supports JSON
  mode, its max tokens, and temperature limits are queried per model, so Atlas requests JSON
  mode only where supported and degrades gracefully elsewhere.
- **Adaptive timeouts** scaled by expected token count and a per-provider factor (a long
  tailoring call gets more time than a one-line classify).
- **Single `resolve_api_key()` path**: keys come from the keyring and are passed to LiteLLM
  **directly, never via `os.environ`**. **Local providers (Ollama/LM Studio) deliberately
  skip the env-key fallback** so a paid cloud key can never leak to a local endpoint.
- Because it sits behind `LLMProvider`, the rest of Atlas is agnostic to LiteLLM; it could be
  swapped for direct SDKs later without touching callers.

**Cross-cutting AI features**

- **Provider-agnostic prompt library** (`atlas/ai/prompts/`): every AI task is a versioned
  prompt template + expected output schema.
- **Structured output contract** (a `complete_json()` helper shared by every backend):
  Atlas requests JSON against a Pydantic-derived schema and validates the response, with a
  layered recovery strategy before it gives up:
  1. **Happy path** — read the backend's native structured field (CLI `structured_output` /
     LiteLLM JSON mode) and validate against the schema.
  2. **Brace-balancing extraction** — if the payload is wrapped in prose or a code fence,
     extract the first balanced JSON object (`_extract_json`-style) and re-validate.
  3. **Content-quality retry** — on malformed/truncated JSON, retry a bounded number of
     times, **escalating temperature** slightly to break a stuck deterministic failure.
  4. **JSON-mode → prompt-only fallback** — if a model's JSON mode misbehaves, drop to a
     plain prompt that instructs "return only JSON between delimiters" and extract from that.
  5. Only then surface a clear error (and optionally fail over to the next backend).
  These are **content** retries, distinct from the Router's **transport** retries (above).
- **Cost/latency accounting**: usage recorded per call when available; per-day and
  per-application cost visible in the TUI; configurable spend caps for API backends.
- **Caching**: content-addressed cache keyed on (prompt template version, model, inputs)
  so re-opening a posting doesn't re-spend on identical calls.
- **Failover chain**: ordered list of backends; on hard error/timeout, try the next.
- **Redaction**: an optional pre-send scrubber can strip PII (phone, address) from prompts
  for tasks that don't need it.

### 5.2 Onboarding & Preferences (`atlas.profiles`)

Q&A wizard capturing, per profile:

- **Target roles / titles** and acceptable variants.
- **Seniority / skill level** (intern, new-grad, junior, mid, senior, staff+…).
- **Field / specialization** (backend, frontend, full-stack, ML/AI, data, infra/SRE,
  security, mobile, embedded…).
- **Location**: cities, on-site/hybrid/remote, remote regions, timezone constraints,
  relocation willingness.
- **Compensation**: salary floor/target, currency, equity/bonus attitude.
- **Work authorization / visa** needs (drives filtering; never fabricated on resumes).
- **Company preferences**: size (startup↔big-tech), industry likes/avoids, mission/culture
  keywords.
- **Deal-breakers** (e.g. no on-call, no relocation, min salary, specific tech to avoid).
- **Tailoring emphasis**: which themes to foreground (e.g. "distributed systems",
  "product sense") per profile.

Stored as structured records; editable anytime via TUI (`Settings → Profile`) or
`atlas profile edit`. Preferences feed both deterministic pre-filters and the AI scoring
prompt.

### 5.3 Master Resume Handling (`atlas.resume`)

> **Model:** exactly **one master resume** per user, shared across all profiles. Profiles
> differ only in preferences, match criteria, and tailoring emphasis — they all draw
> content from the same master. (Multiple distinct master resumes are explicitly out of
> scope; the schema keeps `master_resume` singular-per-user.)

- Input: a single **Markdown** file (path watched for changes) or pasted content.
- **Parser** splits it into structured, addressable blocks: contact/header, summary,
  experiences (each with company, title, dates, bullet list), projects, skills (grouped),
  education, certifications, publications, links. Uses heading conventions + AI-assisted
  structure extraction as a fallback for messy formatting.
- Each bullet/achievement gets a stable **content ID** so tailoring decisions and honesty
  validation can trace back to source content.
- Versioned: edits create a new master-resume version; past tailored resumes remember
  which version they were built from.
- Optional structured "brag doc" fields (metrics, tech tags per bullet) that improve
  matching but aren't required.

### 5.4 Job Discovery (`atlas.discovery`)

Two complementary strategies, both feeding one normalized `JobPosting` model.

**A) Company watchlist (per-company ATS)**

- User adds companies; Atlas auto-detects and stores each company's ATS board URL/token.
- **ATS source adapters** for the stable, structured boards:
  - **Greenhouse** (public boards JSON API)
  - **Lever** (public postings API)
  - **Ashby** (public job board API)
  - **Workday** (per-tenant CxS endpoints)
  - **SmartRecruiters**, **Recruitee**, **Personio** (extensible adapter interface)
- Each adapter: list postings → normalize → dedupe by external id.

**B) Aggregator keyword search**

- Atlas ships adapters for **all** supported aggregators; the user decides which to enable.
  Key-gated sources are simply inactive until the user pastes a key — Atlas never requires
  the user to pay, and clearly labels which sources are free vs. key-gated:
  - **Free / no key**: **RemoteOK**, **Remotive** (feeds), **Hacker News "Who is hiring"**
    parsing, **arbeitnow**, and similar.
  - **Free key required**: **Adzuna** (app id + key), **USAJOBS** (email + key), etc.
  - **Paid key**: any commercial aggregator the user chooses to subscribe to.
- Keys are pasted during setup or in Settings and stored in the **OS keychain** (never in
  config). A source with no key is shown as "needs API key" rather than failing silently.
- Extensible adapter interface; each adapter documents its auth, rate limits, and free/paid
  status, surfaced in the Settings → Job Sources screen.
- User defines saved searches (keywords + location + filters) per profile.

**Scraping (later phase, behind a flag)**

- Optional headless-browser scraping of mainstream boards (e.g. LinkedIn/Indeed) is
  **disabled by default**, clearly flagged as ToS-risky and fragile, rate-limited, and
  never automates login or submission. Off unless the user explicitly opts in.

**Pipeline**: schedule → fetch (respecting robots/rate limits & per-source backoff) →
normalize → dedupe (by external id + fuzzy title/company/URL hash) → deterministic
pre-store → AI scoring (§5.6) → persist → notify TUI. Dedup also spans strategies so the
same role from watchlist and aggregator collapses into one entry.

### 5.5 Scraper & Posting Parser (`atlas.scrape`)

Turns a URL (user-pasted or discovered) into a normalized `JobPosting`.

- **Fetcher**: `httpx` for static pages; **Playwright** headless Chromium fallback for
  JS-rendered pages. Polite: user-agent identification, per-domain rate limiting, robots
  awareness, caching.
- **Extractor**: prefer structured data first — **JSON-LD `JobPosting` schema.org**,
  OpenGraph, and known-ATS DOM patterns — then fall back to readability-style main-content
  extraction, then an **AI extraction pass** that maps messy text into the structured
  fields.
- **Normalized fields**: title, company, location(s)/remote, employment type, seniority,
  salary (if present), full description text, responsibilities, requirements
  (must/nice-to-have), tech stack/keywords, team, posted date, apply URL, source, raw HTML
  snapshot.
- Stores a raw snapshot so re-parsing is possible without re-fetching.

### 5.6 Match / Fit Engine (`atlas.matching`)

Per the chosen approach, **the AI scores every candidate posting** (no hard pre-filter
that silently drops jobs).

- For each new posting + active profile, Atlas sends the normalized posting + the profile
  preferences + a compact summary of the master resume to the AI and requests a
  **structured fit assessment**:
  ```json
  {
    "score": 0-100,
    "verdict": "strong | good | stretch | weak",
    "rationale": "2-4 sentences",
    "matched_strengths": ["..."],
    "gaps": ["missing keyword/skill/requirement", "..."],
    "dealbreaker_hits": ["..."],
    "salary_fit": "above | within | below | unknown"
  }
  ```
- Deterministic signals (salary floor, location, work-auth, explicit deal-breakers) are
  computed too and **passed into the prompt as context** and shown as badges — they inform
  and annotate the score but don't pre-discard, so the user always sees everything with a
  reason.
- **Cost controls** (important, since every job is scored): scoring uses a cheaper/faster
  model tier where available; results are cached; batching where the backend supports it;
  a per-day scoring budget with a queue so a flood of postings can't blow the cost cap
  (overflow is queued and reported, never silently dropped).
- Output persisted with each posting; the Discover queue is sorted by score, filterable by
  verdict, and shows the rationale inline.

### 5.7 Resume Tailoring (`atlas.tailor`)

Given a `JobPosting` + master resume + profile emphasis, produce a **one-page** tailored
resume.

**Two tailoring modes** (pattern adapted from Resume-Matcher, §19):

- **Diff mode (preferred)** — when the master resume is well structured (parsed into blocks
  with content IDs), the AI produces a **skill-target plan** (which posting requirements to
  hit) → generates **targeted diffs** against specific blocks → Atlas **applies** them →
  a **verify** pass confirms the result. Small, reviewable, traceable edits rather than a
  wholesale rewrite; each diff is attributable to a content ID and a reason.
- **Full-output fallback** — if structured data is thin or diff mode fails validation, fall
  back to generating the full tailored content in one pass.

The pipeline in either mode:

1. **Relevance selection**: AI ranks master-resume bullets/projects/skills by relevance to
   the posting's requirements and keywords, returning selections **by content ID** with
   per-item reasons.
2. **One-page fit**: an iterative packing step selects the highest-value content that fits
   one page for the chosen template. If content overflows, Atlas trims lowest-relevance
   items and can tighten wording; if underflows, it promotes more content. The renderer
   reports measured page count and the loop adjusts (bounded iterations).
3. **Rewording / emphasis**: bullets may be rephrased to surface job-relevant keywords and
   impact. Governed by the **honesty setting** (§11): the configured level controls how
   far rephrasing/inference may go, from "reword existing facts only" to "light inference
   of adjacent skills."
4. **Keyword alignment (ATS)**: ensures relevant real keywords from the posting appear
   where truthfully supported; reports which desired keywords could **not** be truthfully
   included (feeding gap suggestions).
5. **Refinement & AI-phrase scrub**: a final pass injects still-missing supported keywords,
   checks alignment, and **scrubs AI-tell phrasing** (generic filler like "leveraged
   synergies", "spearheaded a plethora") so the output reads like the user, not a model.
6. **Local safety nets (defense-in-depth, deterministic — not the LLM)**: after generation,
   Atlas re-validates that **personal info, employment dates, real skills, and custom
   sections were preserved** and not dropped or altered by the model. A specific known
   failure it guards: **LLMs silently drop month precision on dates**, so Atlas restores
   dates from the source master resume. This runs regardless of honesty level and feeds
   §11's traceability check.
7. **Output**: a structured `TailoredResume` (selected content + final wording + layout
   hints) plus a diff view vs. the master, an explanation of every include/exclude/reword
   decision, and the rendered PDF (§5.11).

The user can edit any bullet, pin/exclude items, re-run a section, or override wording;
edits are preserved and re-rendered.

### 5.8 Cover Letter Generation (`atlas.coverletter`)

- Inputs: posting, tailored resume selections, profile, company context (from the
  posting + optional user notes), and a user-selected **tone/length** and optional
  template.
- Produces a structured letter (greeting, hook, 2–3 body paragraphs mapping the user's
  real strengths to the role's needs, close) with the same honesty guardrails.
- Editable inline; regenerate per paragraph; export to PDF (matching resume styling) and
  Markdown/plain text for pasting into web forms.

### 5.9 Application-Question Drafting (`atlas.questions`)

- User pastes the posting's form questions (e.g. "Why this company?", "Describe a technical
  challenge"). Atlas detects/normalizes them (also auto-extracts likely questions from the
  scraped posting when present).
- Drafts tailored answers grounded in the master resume + posting, honoring length limits
  the user specifies, in the user's voice.
- Answers are stored **with the application** and editable. A **reusable answer library**
  remembers strong answers to recurring prompts and adapts them to each new posting
  (so answering "Why do you want to work here?" gets faster over time).

### 5.10 (reserved)

*Auto-submission is intentionally omitted — Atlas prepares materials only; the user submits
manually and marks the application Applied.*

### 5.11 Rendering Pipeline (`atlas.render`)

HTML/CSS → PDF (chosen approach).

- **Templating**: Jinja2 HTML templates + CSS themes. Ships with several clean, ATS-safe
  one-page resume themes and cover-letter themes; users can add their own template dirs.
- **Renderer**: **WeasyPrint** as the pure-Python default (no browser needed); optional
  **headless Chromium (Playwright) print-to-PDF** backend for pixel-perfect / advanced CSS.
  Selectable in config.
- **One-page enforcement**: renderer reports measured page count/overflow back to the
  tailoring loop (§5.7) so content packing converges to exactly one page.
- **Outputs**: PDF (primary), plus HTML and Markdown/plain-text variants. Optional DOCX
  export (later phase) for sites requiring Word uploads.
- **Live preview** in the TUI: render to PDF and show it in the user's default viewer, plus
  an in-terminal text/structure preview; hot-reload on edits.
- **Naming & storage**: exported files use a predictable scheme
  (`Sam_Lee__Company__Role__2026-08-01.pdf`) under the application's folder.

### 5.12 Application Tracking (`atlas.tracking`)

- Every prepared/added job becomes an **Application** with a **status state machine**:
  `Saved → Preparing → Ready → Applied → OA → Interview(1..n) → Offer / Rejected /
  Withdrawn / Ghosted`. Custom stages allowed per profile.
- Each application stores: the posting snapshot, tailored resume + cover letter + Q&A
  versions, status history (timestamped), deadlines (OA due, interview times), contacts
  (recruiter/hiring manager), notes/journal, and outcome.
- **Kanban board** and **table** views in the TUI; filter by profile/status/company;
  full-text search.
- **Reminders/nudges**: "3 apps in Ready but not Applied", "OA due in 24h",
  "no response in 21 days — follow up?".
- **Analytics** (later phase): funnel conversion by stage, response rates by
  company/source, time-in-stage, which tailoring emphases correlate with responses.

### 5.13 Status Detection via Email Scan (`atlas.email`) — optional

- **Generic IMAP first** (chosen): user supplies host/port/username + an app password
  (stored in the OS keychain). Add Gmail API later.
- **Read-only**: Atlas only reads; it never sends or deletes mail.
- Scans on the daemon's schedule for messages related to tracked applications (matched by
  company domain, role keywords, thread refs). An AI classification pass labels each
  relevant message as: application received, OA/assessment invite (+ extract due date &
  link), interview scheduling (+ proposed times), offer, or rejection.
- Proposes status changes and calendar events; **user confirms** before Atlas advances a
  status or writes an event (auto-apply is an opt-in per-user setting).
- Privacy: only headers + bodies of plausibly-relevant messages are read; matching is
  local; the AI classification prompt can be limited to subject + a short snippet.

### 5.14 Calendar Integration (`atlas.calendar`)

- **Generic CalDAV** (chosen): works with iCloud, Fastmail, Google (via CalDAV), Nextcloud,
  etc. User provides CalDAV URL + credentials (app-specific password where required),
  stored in keyring. Library: `caldav`.
- Atlas creates/updates events for OAs, interviews, and deadlines, with configurable
  reminders (VALARMs) and links back to the application.
- Two-way-ish: Atlas owns events it creates (tagged), can update/cancel them, and reads
  them to show a unified schedule in the TUI.
- **`.ics` export fallback** always available for anyone who doesn't want to wire up
  CalDAV — generate an invite file to import manually.

### 5.15 Configuration & Secrets (`atlas.config`)

- Human-editable **TOML** config at an XDG-compliant path
  (`~/.config/atlas/config.toml`), plus per-profile config.
- **Secrets never in the config file**: API keys, IMAP/CalDAV passwords, OAuth tokens live
  in the **OS keychain** via the `keyring` library. Config references them by handle.
- `atlas config` / `atlas doctor` for viewing and validating configuration and backend
  availability.

### 5.16 Desktop Notifications (`atlas.notify`)

Native OS notifications fired by the daemon so the user is alerted even when the TUI is
closed (chosen over TUI-only badges).

- **Library**: **`desktop-notifier`** (PyPI, MIT) — one async, cross-platform API over the
  native backends: **Linux** D-Bus (`org.freedesktop.Notifications`), **macOS** Notification
  Center, **Windows** WinRT. It supports clickable notifications, action buttons, callbacks
  (`on_clicked`/`on_pressed`/`on_dismissed`), urgency levels, sounds, threads (grouping),
  and a max-count limit — and **degrades gracefully**, silently ignoring unsupported
  features rather than raising. Fits the async daemon naturally; a thin `Notifier` wrapper
  adds a no-op fallback if no backend is usable.
- **Triggers** (all individually toggleable, with quiet hours & a daily cap to avoid
  spam): new match at/above a fit-score threshold, OA/interview deadline approaching,
  "ready but not applied" nudge, no-response follow-up reminder, and email-scan-detected
  status changes awaiting confirmation.
- **Actionable**: notifications carry buttons/click callbacks (via `desktop-notifier`) that
  open the TUI focused on the relevant item; where a backend lacks actions it degrades to
  an informational toast and the item is flagged in the TUI.
- **macOS packaging caveat**: on macOS 10.14+, only **signed** executables can post
  notifications — the python.org build is signed, **Homebrew Python is not**. Documented in
  install docs; the no-op fallback means Atlas still runs (notifications just don't appear)
  if run under an unsigned interpreter.
- The TUI still shows badges/alerts; desktop notifications are the daemon's out-of-app
  channel, not a replacement for in-app surfacing.

---

## 6. Data Model (SQLite)

Modeled with **SQLModel** (one class per table, doubling as the Pydantic model and the
SQLAlchemy table — SQLModel is a thin wrapper over both) and migrated with **Alembic**.
Core tables (simplified):

- **user** — single row: name, contact, global settings.
- **profile** — id, name, preferences (JSON), tailoring_emphasis, match_criteria,
  active flag.
- **master_resume** — id, version, source_path, raw_markdown, parsed structure (JSON),
  created_at.
- **resume_block** — id, master_resume_id, type (experience/project/skill/…), content_id
  (stable), text, tags/metrics (JSON) — enables traceability.
- **company** — id, name, ats_type, ats_board_ref, domain, notes.
- **job_source** — id, type (ats/aggregator/url/scrape), config (JSON), profile_id,
  enabled, last_polled_at.
- **job_posting** — id, external_id, source_id, company_id, title, location, remote_type,
  employment_type, seniority, salary (JSON), description, requirements (JSON),
  keywords (JSON), apply_url, posted_at, raw_snapshot_ref, fetched_at, dedupe_hash.
- **match_score** — id, job_posting_id, profile_id, score, verdict, rationale,
  matched_strengths (JSON), gaps (JSON), dealbreaker_hits (JSON), salary_fit,
  signals (JSON), model, created_at. (`salary_fit` is the AI's salary verdict and
  `signals` holds the computed deterministic signals — salary / location /
  work-auth / deal-breakers — so §5.6's badges render on re-view without
  recomputing against a since-changed profile. Rows are **append-only**: re-scoring
  inserts a new row and the latest is surfaced, preserving fit history.)
- **application** — id, job_posting_id, profile_id, status, status_history (JSON),
  applied_at, outcome, notes, created_at, updated_at.
- **tailored_resume** — id, application_id, master_resume_version, selections (JSON),
  final_content (JSON), rendered_pdf_ref, decisions (JSON), edited_by_user flag, version.
- **cover_letter** — id, application_id, content, tone, rendered_pdf_ref, version.
- **application_answer** — id, application_id, question, answer, source_library_id?,
  version.
- **answer_library** — id, prompt_pattern, canonical_answer, tags.
- **calendar_event** — id, application_id, type (oa/interview/deadline), starts_at,
  ends_at, caldav_uid, reminder_minutes, synced_at.
- **email_match** — id, application_id, message_uid, classification, extracted (JSON),
  handled flag.
- **ai_call** — id, task, prompt_version, backend, model, tokens/cost, latency,
  cache_hit, created_at (observability & spend caps).
- **alembic_version** — Alembic migration bookkeeping.

Files (resumes, PDFs, HTML snapshots) live under the data dir
(`~/.local/share/atlas/`); the DB stores references, not blobs.

---

## 7. AI Task Contracts

Each task is a versioned prompt template + JSON output schema, validated on return.

| Task | Inputs | Output schema (summary) |
|---|---|---|
| `parse_master_resume` | raw Markdown | structured sections + blocks with content IDs |
| `parse_job_posting` | messy page text | normalized JobPosting fields |
| `score_fit` | posting + profile + resume summary | score, verdict, rationale, strengths, gaps, dealbreakers |
| `select_resume_content` | posting + resume blocks + emphasis | ranked selections by content ID + reasons |
| `reword_bullets` | selected blocks + posting + honesty level | reworded text + change log |
| `write_cover_letter` | posting + selections + tone | structured letter |
| `draft_answers` | questions + posting + resume + library | answers + which library entries reused |
| `classify_email` | subject + snippet + app context | label + extracted dates/links |
| `honesty_validate` | tailored content + master blocks | list of unsupported claims (traceability) |

Every task: bounded JSON-repair retries, response caching, usage logging, and a graceful
degraded mode (e.g. if `parse_job_posting` fails, keep the raw text and let the user fix
fields).

---

## 8. TUI Design (Textual)

**Global chrome**: left nav sidebar, top status bar (active profile, daemon status, today's
deadlines, AI backend + spend), command palette (`Ctrl+P`), context help (`?`), vim-style
and arrow navigation, light/dark themes.

**Screens**

1. **Dashboard** — pipeline funnel counts, upcoming deadlines, new matches badge, recent
   activity, daemon/backend health.
2. **Discover** — ranked queue of scored postings; columns for score/verdict/company/
   title/location/salary/source; inline rationale; actions: open, tailor, dismiss, save.
3. **Posting detail** — full parsed posting, fit rationale, strengths/gaps, apply link,
   "Tailor" action.
4. **Tailor workspace** — three panes: (a) master resume, (b) tailored selections/diff with
   include/exclude/pin + per-item reason, (c) live PDF/text preview with page-count meter;
   tabs for Resume / Cover Letter / Questions; regenerate-section buttons; export.
5. **Applications (Pipeline)** — Kanban by status + table view; drag/keyboard to move
   stages; filters/search.
6. **Application detail** — status timeline, materials versions, deadlines, contacts,
   notes/journal, calendar events, email matches.
7. **Calendar** — agenda + month view of OAs/interviews/deadlines; create/edit events.
8. **Profiles** — manage multiple profiles + preferences Q&A editor.
9. **Master resume** — view/edit path, re-parse, version history.
10. **Settings** — AI backends (detect/test/order/failover), job sources & watchlist,
    email, calendar, rendering theme, honesty level, spend caps, privacy toggles.
11. **Onboarding wizard** — first-run Q&A flow.
12. **Activity/Logs** — daemon activity, AI calls, costs, errors.

Long-running actions (scoring, tailoring, rendering) run async with progress indicators and
never block the UI; results stream in.

---

## 9. CLI Surface (Typer)

Scriptable equivalents to TUI actions:

```
atlas init                         # onboarding wizard
atlas tui                          # launch full TUI (default when run bare)
atlas doctor                       # validate backends, config, integrations

atlas daemon start|stop|status     # background poller
atlas profile list|add|edit|use    # manage profiles

atlas resume set <path>            # set/point at master resume
atlas resume reparse

atlas company add <name|url>       # add to watchlist (auto-detect ATS)
atlas source add <aggregator> ...  # add a saved keyword search
atlas discover                     # run a poll now
atlas add <url>                    # scrape + score one posting

atlas score <job_id>               # (re)score
atlas tailor <job_id> [--tone ...] # generate resume + cover letter + answers
atlas render <application_id>      # (re)render PDFs
atlas open <application_id>        # open exported files

atlas apply mark <application_id>  # mark Applied (records date)
atlas status set <application_id> <stage> [--due <date>]
atlas list [--status ...] [--profile ...]

atlas cal sync                     # push/pull CalDAV events
atlas email scan                   # run inbox scan now

atlas config get|set
```

`--json` on read commands for scripting; consistent exit codes.

**Output styling.** All human-facing CLI output is rendered with **Rich** (tables, panels,
themed color, progress) for a polished, *visually consistent* experience across every
command — never bare unstyled prints. A single shared console + named theme
(`atlas/cli/console.py`) centralizes the palette via semantic style names (`success`,
`error`, `heading`, …), so all commands match; errors go to a stderr console. `--json` (and
other machine-readable) output is the deliberate exception — emitted unstyled so it stays
pipe/parse-safe. See [`AGENTS.md` §10](../AGENTS.md#10-code-style--conventions).

---

## 10. Configuration Example

```toml
# ~/.config/atlas/config.toml
[ai]
default_backend   = "claude_code"    # Phase 0 default CLI
failover          = ["openrouter"]   # Phase 0 default API
scoring_model_tier = "fast"          # cheaper model for bulk scoring
daily_spend_cap_usd = 5.0            # applies to API backends

[ai.backends.claude_code]
type = "cli"
command = "claude"
output_format = "json"               # + --json-schema per task
# uses existing Claude Code login; set use_bare=true for ANTHROPIC_API_KEY path

[ai.backends.openrouter]
type = "api"
model = "anthropic/claude-sonnet"
# api key -> keyring handle "atlas:openrouter"

# Other CLI backends (codex, antigravity) and API backends (bedrock, anthropic,
# openai-compatible) are configured the same way; see Appendix A.

[logging]
level = "WARNING"                    # console level; --log-level / -v / ATLAS_LOG_LEVEL override
file_enabled = true                  # rotating log file under the state dir (always DEBUG+)
max_bytes = 1000000                  # rotate the log file at ~1 MB
backup_count = 3                     # rotated files to keep

[render]
engine = "weasyprint"                # or "chromium"
resume_theme = "jakes-resume"        # ships as the default one-page theme
cover_theme  = "matching"

[tailoring]
honesty_level = "light_inference"    # strict | reword_only | light_inference
enforce_one_page = true

[discovery]
poll_interval_minutes = 120
enable_scraping = false              # ToS-risky sources off by default

[integrations.calendar]
type = "caldav"
url  = "https://caldav.example.com/user/calendar"
# credential -> keyring

[integrations.email]
enabled = true
protocol = "imap"
host = "imap.example.com"
scan_interval_minutes = 60
auto_apply_status = false            # propose, don't auto-change

[notifications]
enabled = true                       # native desktop notifications from the daemon
min_match_score = 80                 # only notify for matches at/above this fit score
deadline_lead_hours = 24
quiet_hours = "22:00-08:00"
daily_cap = 20
```

---

## 11. Honesty / Truthfulness Controls

Resume/cover-letter/answer generation is governed by a configurable **honesty level**:

- **`strict`** — select/reorder/reword existing master-resume facts only; never introduce
  skills or claims not present. A `honesty_validate` pass flags any output claim not
  traceable to a master `resume_block` content ID.
- **`reword_only`** — same, but freer rephrasing for impact and keyword surfacing, still no
  new facts.
- **`light_inference`** *(selected default)* — may infer clearly-adjacent skills and phrase
  aggressively for keyword match. Higher ATS keyword hit rate.

Regardless of level, Atlas always:

- Runs the traceability validator and **flags** any claim it can't trace to the master, so
  the user sees exactly what was inferred/added and can accept or reject it.
- Runs the **deterministic local safety nets** (§5.7 step 6) that preserve personal info,
  employment dates (including the month-precision restore), real skills, and custom
  sections — a non-LLM backstop so the model can't silently drop or corrupt factual content.
- Produces **gap suggestions** — desired job keywords/skills that were *not* truthfully
  supportable — so the user can add real ones to the master resume.

> **Design note / recommendation:** `light_inference` maximizes keyword matching but carries
> real risk of a resume claiming something the user can't back up in an interview. The
> validator + flags exist specifically to mitigate this. The level is a per-profile setting;
> Atlas recommends `strict` or `reword_only` for anything the user will be grilled on, and
> makes every inferred claim visible before export. Default ships as configured
> (`light_inference`) but is one setting away from strict.

---

## 12. Security, Privacy & Legal

- **Local-first**: all personal data on-device (SQLite + files). No Atlas cloud.
- **Secrets in OS keychain** (`keyring`), never in config or DB. Optional full at-rest
  encryption (SQLCipher/passphrase) is a documented later-phase upgrade.
- **AI data flow transparency**: the TUI shows exactly which backend receives prompts.
  API backends send data to that vendor; CLI backends use the user's own tool auth. An
  optional PII redactor strips contact details from prompts that don't need them.
- **Email**: read-only, opt-in, app-password in keychain, only relevant messages parsed.
- **Calendar**: only Atlas-created events are modified; credentials in keychain.
- **Legal/ToS posture**: default sources are ATS public boards, legitimate aggregator
  APIs, and user-pasted URLs — the stable, low-risk paths. Mainstream-board scraping is
  **off by default**, gated behind an explicit opt-in flag with an in-app warning, rate
  limited, and never logs into or submits to any site. Atlas **never auto-submits
  applications** and never automates account logins. robots.txt and per-domain rate limits
  are respected by the fetcher.

### 12.1 Cross-Platform Support (Windows · macOS · Linux)

Atlas is a **first-class citizen on all three OSes**. Platform-specific concerns and their
abstractions:

| Concern | Windows | macOS | Linux |
|---|---|---|---|
| **Paths** | `%APPDATA%` / `%LOCALAPPDATA%` | `~/Library/Application Support` | XDG dirs |
| **Secrets** (`keyring`) | Windows Credential Manager | macOS Keychain | Secret Service / kwallet (with an encrypted-file fallback for headless boxes) |
| **Daemon / autostart** | Task Scheduler or a Windows service (via a lightweight service wrapper) | `launchd` LaunchAgent | `systemd --user` unit; cron fallback |
| **Notifications** (§5.16) | `desktop-notifier` → WinRT | `desktop-notifier` → Notification Center (needs signed interpreter) | `desktop-notifier` → D-Bus |
| **PDF render (WeasyPrint)** | ships GTK/Pango deps; documented installer or the Chromium renderer fallback | Homebrew deps or Chromium fallback | system libs or Chromium fallback |
| **Terminal / TUI** | Windows Terminal recommended (Textual supports it); legacy conhost degraded | Terminal/iTerm2 | any modern terminal |

- A `platform` abstraction module isolates every OS-specific call (paths, keyring backend
  selection, daemon install, notifier, file-open) behind one interface so the rest of the
  code stays OS-agnostic.
- **Path handling** uses `platformdirs` for config/data/cache/state locations rather than
  hardcoded `~/.config`.
- **WSL note**: WSL2 (the dev environment) is treated as Linux, with a documented caveat
  that desktop notifications and the coding CLIs must be reachable from inside WSL.
- CI runs the test matrix on Windows, macOS, and Linux runners.

---

## 13. Technology Stack

| Concern | Choice |
|---|---|
| Language | Python 3.11+ |
| Project & dependency management | **uv** (lockfile, venv, `uv run`/`uv sync`/`uv add`, `uv build`) |
| TUI | **Textual** (+ **Rich**) |
| CLI | **Typer** (+ **Rich** for styled, consistent output — shared console/theme) |
| Models, DB & migrations | **SQLModel** (Pydantic + SQLAlchemy in one) over **SQLite** (WAL) + **Alembic** |
| Scheduler (daemon) | **APScheduler** |
| HTTP | **httpx** |
| JS-page scraping | **Playwright** (headless Chromium) |
| HTML extraction | selectolax/BeautifulSoup + readability + JSON-LD |
| Rendering | **WeasyPrint** (default) / Playwright print (optional) |
| Templating | **Jinja2** + CSS themes |
| Secrets | **keyring** (Credential Manager / Keychain / Secret Service) |
| Cross-platform paths | **platformdirs** |
| Desktop notifications | **`desktop-notifier`** (async; WinRT · macOS Notification Center · D-Bus) |
| Calendar | **caldav** + `icalendar` |
| Email | **imaplib**/`imap-tools` (Gmail API later) |
| AI — CLI | `subprocess` adapters for claude/codex/antigravity (all support `--output-format json` + JSON schema; see Appendix A) |
| AI — API | **LiteLLM** (`Router` + `RetryPolicy`) behind Atlas's `LLMProvider` interface — OpenRouter, Bedrock, Anthropic, Gemini, DeepSeek, Groq, Ollama, OpenAI-compat |
| Prompt templating | **Jinja2** (versioned templates + JSON schemas per AI task) |
| Doc → text (optional resume import) | `markitdown` (DOCX) + `pdfminer.six` (PDF) — for ingesting non-Markdown master resumes later |
| Packaging & distribution | `uv build` → PyPI; install via `uv tool install atlas` / `pipx install atlas` (all-OS) |
| Testing | **pytest**, `pytest-asyncio`, `respx` (mock httpx/LiteLLM), `pytest-textual`, recorded HTTP fixtures, fake AI provider |
| Lint/format/type | **ruff**, **mypy --strict** |

---

## 14. Proposed Project Layout

```
atlas/
├─ pyproject.toml             # uv-managed project metadata + deps
├─ uv.lock                    # uv lockfile (committed)
├─ README.md                  # overview + doc navigation
├─ LICENSE
├─ docs/                      # see docs/README.md for the index
│  ├─ PROJECT.md              # this document
│  └─ cli-reference/          # coding-CLI headless docs (claude-code, codex, antigravity)
├─ src/atlas/
│  ├─ __main__.py             # CLI entry (Typer)
│  ├─ config/                 # config + secrets (keyring)
│  ├─ db/                     # SQLModel models, session, Alembic migrations
│  ├─ ai/
│  │  ├─ base.py              # LLMProvider protocol, request/response
│  │  ├─ complete_json.py     # structured-output contract + repair/fallback
│  │  ├─ cli/                 # claude, codex, antigravity subprocess adapters
│  │  ├─ api/                 # LiteLLMProvider (Router + RetryPolicy), key resolution
│  │  ├─ prompts/             # versioned Jinja2 templates + JSON schemas per task
│  │  ├─ cache.py  router.py  # caching + failover chain
│  ├─ profiles/               # onboarding Q&A, preferences
│  ├─ resume/                 # master resume parse/version
│  ├─ discovery/
│  │  ├─ ats/                 # greenhouse, lever, ashby, workday, ...
│  │  ├─ aggregators/         # adzuna, usajobs, remoteok, ...
│  │  └─ poller.py
│  ├─ scrape/                 # fetch + extract → JobPosting
│  ├─ matching/               # score_fit engine
│  ├─ tailor/                 # selection, reword, one-page packing
│  ├─ coverletter/
│  ├─ questions/              # + answer library
│  ├─ render/                 # HTML/CSS → PDF, themes
│  ├─ tracking/               # applications, status machine, analytics
│  ├─ calendar/               # CalDAV + ics
│  ├─ email/                  # IMAP scan + classify
│  ├─ daemon/                 # scheduler + IPC server
│  └─ tui/                    # Textual app, screens, widgets
└─ tests/
```

---

## 15. Phased Roadmap

The document specs everything; build order is phased. Each phase is independently useful.

> **Live status:** [`docs/STATUS.md`](./STATUS.md) tracks the current phase and the concrete
> next step. The checkboxes below are the durable per-item ledger; tick them as work lands
> (part of the [Definition of Done](../AGENTS.md#8-definition-of-done)).

### Phase 0 — Foundations
- [x] **Repository hygiene & CI (do this first).** Establish the `.github/` setup and quality
  gates that every later PR depends on (`AGENTS.md` already assumes these exist):
  - [x] `.github/workflows/ci.yml` — GitHub Actions running `ruff` (format check + lint),
    `mypy --strict`, and `pytest` with the 100% line/branch coverage gate, on the
    Windows/macOS/Linux matrix, driven by `uv`.
  - [x] Root `.pre-commit-config.yaml` mirroring those checks for fast local gating.
  - [x] `.github/pull_request_template.md` mirroring the Definition of Done checklist in
    [`AGENTS.md`](../AGENTS.md), and `.github/ISSUE_TEMPLATE/` (bug + feature + `config.yml`).
  - [x] `.github/dependabot.yml` (uv/pip + GitHub Actions), `.github/CODEOWNERS`, and `main`
    branch protection (require green CI + review; merge-commit strategy).
  - [x] Root `CHANGELOG.md` ([Keep a Changelog](https://keepachangelog.com/); referenced by the
    Definition of Done) and `CONTRIBUTING.md` pointing at `AGENTS.md`.
  - *(A `uv build` → PyPI release workflow is deferred until there's something to ship —
    Phase 1+.)*
- [x] Project scaffold with **uv** (`pyproject.toml`, committed `uv.lock`, `uv run` gates),
  the `src/atlas` package, and the `ruff` / `mypy --strict` / `pytest` + coverage config.
- Cross-platform paths (`platformdirs`), config + keyring, **SQLModel** + SQLite (WAL)
  + Alembic, logging:
  - [x] Cross-platform paths (`platformdirs`) + config + keyring (`atlas.config`).
  - [x] **SQLModel** + SQLite (WAL) + Alembic (`atlas.db`).
  - [x] Logging (`atlas.logging`) — Rich console + rotating file to the state dir,
    `[logging]` config, `--verbose`/`--log-level`.
- **AI provider abstraction** with the two chosen Phase 0 backends: **Claude Code** (CLI,
  default) + **OpenRouter** (API, failover). Capability probing, `--output-format json` +
  `--json-schema` structured path, JSON-repair loop, `atlas doctor`:
  - [x] Core contract (`LLMProvider` + `complete_json()` recovery ladder) and the
    `CliAdapter` base + injected `SubprocessRunner` boundary.
  - [x] **Claude Code** CLI adapter (structured path, neutralized tools, `--bare` opt-in).
  - [x] **OpenRouter** API adapter via LiteLLM behind `LLMProvider` (`atlas.ai.api`), with
    per-model capability lookup and the transport/content retry split.
  - [x] Failover chain across the backend order (`atlas.ai.router` — `FailoverProvider` +
    `build_provider_chain`; fails over on `LLMBackendError`/`LLMTimeoutError`, not
    `LLMOutputError`).
  - [x] CLI scaffold (`atlas.cli`, Typer) + **`atlas doctor` v1** reporting each backend's
    availability (`atlas.cli.doctor`).
  - [x] Per-backend capability probing (`atlas.ai.probe` + `atlas.ai.probe_cache`; cached
    round-trip JSON probe, all five capabilities) surfaced through `atlas doctor --probe`.
  - [x] Structured error classification (Claude failures mapped from the stream-json `error`
    category, stderr heuristic fallback) and CLI **version-minimum** enforcement
    (`CliAdapter._minimum_version` / `check_availability`; Claude Code ≥ 2.1.205) — resolves
    §18.2.
- [x] Verified against the real installed `claude` CLI (the `atlas doctor --probe` round-trip;
  Codex/Antigravity adapters and their live verification remain for a later phase).

### Phase 1 — Core loop (first genuinely useful release)
- [x] Onboarding Q&A + preferences; **single** profile (schema already multi-profile).
  (`atlas.profiles` + `atlas init` / `atlas profile list|add|edit|use`; typed
  `ProfilePreferences`, repository, injectable-prompter wizard, DB bootstrap.)
- [x] Master resume ingest + parse + versioning. (`atlas.resume` + `atlas resume
  set|reparse|show`; deterministic Markdown parser into content-ID'd blocks
  behind an AI-fallback seam, immutable monotonic versions, `master_resume` /
  `resume_block` tables.)
- [x] **Paste-URL** scrape + parse (static + Playwright fallback). (`atlas.scrape`
  + `atlas add` / `atlas postings list|show`; injectable `httpx` fetch with a
  `BrowserFetcher` seam for the deferred Playwright fallback, JSON-LD/OpenGraph/
  main-text extraction then the `parse_job_posting` AI pass, `company` /
  `job_source` / `job_posting` tables, on-disk snapshots.)
- [x] **Fit scoring** for a pasted job. (`atlas.matching` + `atlas score` /
  `atlas add` scoring; deterministic salary/location/work-auth/deal-breaker
  signals as prompt context + badges, the `score_fit` AI pass via `complete_json`,
  append-only `match_score` rows, latest score surfaced in `atlas postings`.)
- [x] **Resume tailoring** + **cover letter** + **HTML→PDF rendering** with one-page enforce.
  *(Built as three PRs: **HTML→PDF rendering** ✅ `atlas.render` + `atlas resume render`;
  **resume tailoring** ✅ `atlas.tailor` + `atlas tailor` — the honesty-governed
  `select_and_reword` pass, deterministic date-restore, the render-measure-trim one-page loop,
  and the `application` + `tailored_resume` tables; **cover letter** ✅ `atlas.coverletter` +
  `atlas cover` — the honesty-governed `write_cover_letter` pass grounded in the tailored resume
  (or master resume), the `matching` cover theme, and the `cover_letter` table — plus the
  application-keyed `atlas render` / `atlas open` (`atlas.materials` + the `atlas.platform`
  file-open seam). Deferred to a PR 2b: the `honesty_validate` traceability pass, AI-phrase
  scrub, keyword-gap suggestions, diff-mode, per-profile honesty, and the editable/regenerate
  loop.)*
- [ ] **Application tracking** with manual status + the core TUI (Dashboard, Posting, Tailor
  workspace, Applications, Application detail). *(The `application` table landed with tailoring.
  **Core + CLI ✅** `atlas.tracking` — the `ApplicationStatus` state machine + `can_transition`,
  the transition service recording timestamped `status_history` / `applied_at` / `outcome`
  (validated, with a `--force` override), `list_applications`, and the manual-transition CLI
  `atlas status set` / `atlas apply mark` / `atlas list` (§9); no migration, the schema was
  already in place. **Core TUI ✅** `atlas.tui` (Textual) + `atlas tui` — the Dashboard,
  Applications (table + Kanban), Application-detail, and Posting-detail screens over pure data
  builders (`atlas.tui.data` + reused CLI `build_*`), in-TUI status changes, the async `Pilot`
  test harness (`textual` + `pytest-asyncio`), and `count_applications_by_status` for the funnel.
  **Remaining:** the three-pane **Tailor workspace** (§5.7) + wiring tailoring/cover/score/
  render/open through Textual **thread workers** (those services block).)*

### Phase 2 — Discovery & background
- [ ] **Daemon** + scheduler + IPC.
- [ ] **Company watchlist** + ATS adapters (Greenhouse, Lever, Ashby, Workday).
- [ ] **Aggregator** adapters + saved keyword searches.
- [ ] Dedup + scored **Discover** queue in the TUI.
- [ ] **Multiple profiles** fully wired.

### Phase 3 — Scheduling & status intelligence
- [ ] **CalDAV** calendar integration + `.ics` fallback; Calendar screen.
- [ ] **IMAP email scan** + AI classification → proposed status changes & events.
- [ ] **Application-question drafting** + reusable answer library.

### Phase 4 — Polish & depth
- [ ] Analytics/funnel views; reminders/nudges.
- [ ] More ATS/aggregator adapters; optional **opt-in scraping** behind a flag.
- [ ] DOCX export; more resume/cover themes; PII redactor; at-rest encryption option.
- [ ] Gmail API adapter; additional API backends; batch scoring optimizations.

---

## 16. Testing & Quality

- **Fake AI provider** returning canned structured responses → deterministic tests of
  tailoring/scoring/rendering without spending tokens or network.
- **Recorded HTTP fixtures** for ATS/aggregator/scrape adapters (golden postings); **`respx`**
  to mock httpx/LiteLLM calls at the transport boundary.
- **Renderer snapshot tests**: assert one-page output and stable layout per theme.
- **Schema-contract tests**: every AI task's output validates against its Pydantic schema;
  the `complete_json()` repair/fallback loop tested against malformed/truncated samples.
- **TUI tests** via Textual's testing harness (key flows: onboard, tailor, status move).
- **Honesty validator + safety-net tests**: assert flagged claims trace (or fail to trace)
  to master blocks, and that the date-restore/preservation nets fire correctly.
- **Test markers** (`unit` / `service` / `integration` / `eval`), with **real-LLM `eval`
  tests excluded from the default run** and skipped absent a configured key — matching the
  isolated-by-default policy in `AGENTS.md` §6.
- `ruff` + `mypy --strict` in CI; `pytest` matrix on Windows/macOS/Linux at 100% coverage.

---

## 17. Key Risks & Mitigations

| Risk | Mitigation |
|---|---|
| Coding CLIs aren't stable text APIs; output formats drift across versions | All three support `--output-format json` + JSON-schema (Appendix A) so the happy path is structured; plus capability probing, delimiter-fenced-JSON + repair fallback, per-tool adapter subclasses, version detection in `atlas doctor`, and failover to the API backend. |
| CLI auth quirks (Antigravity needs prior interactive login; Claude `--bare` skips keychain; Codex git-repo requirement) | Per-tool auth handling documented in Appendix A; `atlas doctor` detects unauthenticated/misconfigured backends and gives a fix hint; failover to OpenRouter. |
| Scoring every job gets expensive | Cheaper model tier for scoring, caching, daily spend cap with queue (never silent-drop), optional batch scoring. |
| Web scraping fragility / ToS | Default to ATS + aggregator APIs + user URLs; mainstream scraping off by default & flagged; robots + rate limits; snapshot caching. |
| One-page overflow with rich content | Render-measure-trim loop with bounded iterations; user pinning; template density variants. |
| AI fabrication on resumes | Configurable honesty levels + traceability validator that flags untraceable claims + gap suggestions; recommend strict for high-stakes. |
| Email/calendar credential safety | Keyring only, read-only email, opt-in, app passwords, local matching. |
| Daemon/TUI DB contention | SQLite WAL, single-writer conventions per row class, short transactions. |
| Backend cost/quota surprises | Per-call usage logging, spend caps, TUI cost visibility, failover. |

---

## 18. Resolved Decisions & Remaining Open Questions

### 18.1 Resolved (locked for build)

| Question | Decision |
|---|---|
| Coding-CLI invocations & output envelopes | **Verified** for all three from official headless docs — see [Appendix A](#appendix-a--coding-cli-adapter-reference). All support `--output-format json` + a JSON-schema flag. |
| Which aggregator APIs by default | **Support all**; user opts in and pastes any required keys (free or paid — their choice). Free/no-key sources active out of the box. |
| Multiple master resumes vs. one | **One master resume**, many profiles. Multiple masters out of scope. |
| Interview-prep assistance | **Out of scope** for now (not even Phase 4). May revisit post-v1. |
| Desktop notifications vs. TUI-only | **Native desktop notifications** from the daemon (§5.16), plus in-app badges. |
| Resume honesty default | **`light_inference`** (with traceability validator + flags, §11). |
| Phase 0 backends | **Claude Code** (CLI default) + **OpenRouter** (API failover). |
| Target OS | **Windows, macOS, and Linux** — all first-class (§12.1). |
| API-backend abstraction | **LiteLLM** behind Atlas's `LLMProvider` interface (§5.1a). CLI backends stay custom subprocess adapters. |
| Prompt storage | **Jinja2** templates (not plain Python constants). |
| Structured-output recovery | `complete_json()` layered repair + JSON-mode→prompt fallback (§5.1). |
| Tailoring approach | **Diff mode** preferred, full-output fallback; deterministic post-LLM safety nets (§5.7). |

### 18.2 Remaining open questions (revisit during build)

- ~~Exact CLI **version minimums** to require and how to detect them.~~ **Resolved:**
  `CliAdapter` parses the `--version` output and enforces an overridable per-adapter minimum
  (`_minimum_version` / `check_availability`); Claude Code is pinned to ≥ 2.1.205 (the release
  exposing the stream-json structured `error` category), hard-failed as unavailable when older
  and surfaced with a reason in `atlas doctor`.
- Whether the daemon autostart should be **opt-in during onboarding** or a separate
  explicit `atlas daemon install` step per OS.
- Default **fit-score threshold** for notifications (starting at 80 in the config example —
  validate against real usage).
- Whether to add **DOCX export** earlier than Phase 4 (some application sites require Word
  uploads).
- Post-v1: revisit interview-prep assistance (company research briefs, question banks) if
  users want it.

---

## 19. Reference Projects

### 19.1 Resume-Matcher (srbhr/Resume-Matcher, Apache-2.0)

[Resume-Matcher](https://github.com/srbhr/Resume-Matcher) is the closest existing project to
Atlas and was reviewed as a reference. It's an AI resume-tailoring tool: upload a master
resume (PDF/DOCX), paste a job description, get AI improvements + fit score + cover letter +
interview prep, export PDF. **Web app** (Next.js + FastAPI), `uv`-managed backend, LiteLLM,
TinyDB/SQLite, Playwright PDF.

**How Atlas differs / where it's a superset**

| | Resume-Matcher | Atlas |
|---|---|---|
| Interface | Web app (localhost) | **TUI + CLI** |
| AI backends | LiteLLM (API only) | **Coding CLIs (default)** + LiteLLM for API |
| Scope | tailor · cover letter · score · interview prep | that **+ discovery · tracking · calendar · email · background daemon** |
| Secrets | Fernet-encrypted at rest | OS keyring |
| Rigor | no ruff/mypy | **ruff + mypy --strict + 100% coverage** |

Their scope ≈ Atlas's Phase 1 core loop. Atlas's defining capability — driving the coding
CLIs headlessly — is not something Resume-Matcher does (LiteLLM can't drive them).

**Patterns adopted into this design** (with where they landed):

- **LiteLLM** as the API-backend layer, kept behind Atlas's `LLMProvider` interface — §5.1a.
- **Router-owns-transport-retries; callers own content retries** — §5.1a.
- **Registry-based model capabilities** (JSON mode / tokens / temp), not hardcoded — §5.1a.
- **Single `resolve_api_key()`; local providers skip env-key fallback**; keys never via
  `os.environ` — §5.1a.
- **`complete_json()`** layered structured-output recovery: brace-balancing extraction →
  content-quality retry with temperature escalation → JSON-mode→prompt-only fallback — §5.1.
- **Diff-mode tailoring** (skill-target plan → diffs → apply → verify) with full-output
  fallback — §5.7.
- **Deterministic post-LLM safety nets** preserving personal info / dates / skills / custom
  sections, incl. **month-precision date restore**, and an **AI-phrase scrub** — §5.7, §11.
- pytest markers with **real-LLM (`eval`) tests excluded by default**, and **`respx`** for
  HTTP mocking — reflected in §16 and `AGENTS.md`.
- A rich **`docs/agent/`** documentation layout — Atlas mirrors this (see `docs/agent/`).

**Deliberately not adopted**: web-app architecture (Atlas is TUI-first), TinyDB (Atlas uses
SQLModel), Fernet-at-rest as the primary secret store (Atlas uses the OS keyring; at-rest
encryption remains a later option), and plain-Python-constant prompts (Atlas uses Jinja2).

---

## Appendix A — Coding CLI Adapter Reference

Verified from each tool's official headless/non-interactive documentation (transcribed
under [`docs/cli-reference/`](./cli-reference/): `claude-code.md`, `codex.md`,
`antigravity.md`). **All three expose a
headless JSON mode with a JSON-schema flag**, so Atlas's structured-output contract maps
uniformly onto every backend.

### A.1 Claude Code (`claude`) — *default CLI backend*

- **Invoke**: `claude -p "<prompt>"` (non-interactive "print" mode). Reads stdin too, so
  large context can be piped.
- **Structured output**: `--output-format json --json-schema '<schema>'`. Response is a JSON
  envelope with the text in `result`, structured data in `structured_output`, plus
  `session_id`, `usage`, and **`total_cost_usd`** (+ per-model cost breakdown) for spend
  tracking.
- **Streaming**: `--output-format stream-json --verbose --include-partial-messages`
  (NDJSON; final line is a `result` message).
  > **Atlas implementation note:** the adapter runs
  > `--output-format stream-json --verbose --json-schema` (not plain `json`). Verified against
  > the real CLI: the terminal `result` event still carries `structured_output`, `result`,
  > `usage`, and `total_cost_usd` — so the structured-output contract is preserved — and
  > stream mode additionally exposes the structured `error` category used for failure
  > classification (below), which plain `json` mode does not.
- **Neutralize tools**: pass **no** `--allowedTools` (nothing auto-approved); run in a
  scratch cwd. `--append-system-prompt` / `--append-system-prompt-file` to inject Atlas's
  system instructions; `--system-prompt` to fully replace.
- **Speed/isolation**: `--bare` skips hooks/skills/plugins/MCP/CLAUDE.md discovery for
  reproducible runs — **but also skips OAuth/keychain**, so it needs `ANTHROPIC_API_KEY`.
  Atlas default = non-bare (uses existing login) in an isolated cwd; `use_bare=true` opt-in
  for API-key users.
- **Continue**: `--continue` (most recent) or `--resume <session_id>` (scoped to cwd).
- **Auth**: existing Claude Code login/OAuth by default.
- **Errors**: invalid `--json-schema` exits with a diagnostic; `system/api_retry` events (and
  a failing `assistant` event) in stream mode carry a structured `error` category
  (`authentication_failed`, `rate_limit`, …). Atlas maps this to
  `LLMAuthError`/`LLMRateLimitError`/`LLMBackendError` (stderr-substring heuristic fallback).

Example:
```bash
claude -p "<task prompt>" \
  --output-format json \
  --json-schema '{"type":"object","properties":{...},"required":[...]}'
# -> parse stdout JSON; read .structured_output (or .result), .total_cost_usd, .usage
```

### A.2 OpenAI Codex (`codex exec`)

- **Invoke**: `codex exec "<prompt>"`. Streams progress to **stderr**, prints only the final
  agent message to **stdout**. Reads stdin (prompt-plus-stdin, or `codex exec -` to make
  stdin the whole prompt).
- **Structured output**: `--output-schema <file>` (JSON Schema file) → final stdout message
  conforms to the schema. `-o <path>` / `--output-last-message <path>` also writes the final
  message to a file.
- **Event stream**: `--json` → JSONL stream (`thread.started`, `turn.started`, `item.*`,
  `turn.completed` with a `usage` object, `error`).
- **Neutralize / sandbox**: default sandbox is **read-only** (good for Atlas). Explicit
  `--sandbox read-only`. `--ephemeral` avoids persisting session rollout files.
  `--ignore-user-config` / `--ignore-rules` for a clean automation environment.
- **Git requirement**: Codex must run inside a git repo unless `--skip-git-repo-check` is
  passed — Atlas passes it (or `git init`s the scratch dir).
- **Continue**: `codex exec resume --last` or `codex exec resume <SESSION_ID>`.
- **Auth**: reuses saved CLI auth, or `CODEX_API_KEY=<key>` set **inline for the single
  invocation** (only supported on `codex exec`; keep it out of shared env).

Example:
```bash
codex exec --skip-git-repo-check --sandbox read-only --ephemeral \
  --output-schema ./schema.json -o ./out.json "<task prompt>"
# -> read ./out.json (schema-conformant); parse --json JSONL for usage if needed
```

### A.3 Google Antigravity (`agy`) — *full details in [`cli-reference/antigravity.md`](./cli-reference/antigravity.md)*

- **Invoke**: `agy -p "<prompt>"` (aliases `--print`, `--prompt`). Response on **stdout**,
  diagnostics on **stderr**.
- **Structured output**: `--output-format json --json-schema '<schema-or-file-or-type>'` →
  JSON envelope with `structured_output`, `response` (string), `status`, `usage`,
  `conversation_id`. `--json-schema` accepts a schema string, a `.json` file path, or a
  primitive type name.
- **Streaming**: `--output-format stream-json` → NDJSON (`init` → `step_update`* →
  `result`); concatenate `step_update.text_delta` with `jq -j`.
- **Neutralize tools**: shell commands are **soft-denied by default** in headless mode
  (run continues, exits 0, notice on stderr); workspace file writes are auto-allowed —
  harmless in a scratch workspace. Do **not** pass `--dangerously-skip-permissions`.
- **Model/effort/agent**: `--model <slug>` (list via `agy models`; unknown model fails loud,
  no silent fallback), `--effort low|medium|high`, `--agent <name>`.
- **Continue**: `--continue`/`-c`, or `--conversation <id>`.
- **Timeout**: default **5m**; raise with `--print-timeout 15m`.
- **Auth**: **cached credentials only** — user must authenticate once via an interactive
  `agy` session; an unauthenticated headless run errors with "authentication required".
  `atlas doctor` surfaces this.
- **Status field**: always check `status == "SUCCESS"`; other terminal states are `ERROR`,
  `CANCELED`, `INTERRUPTED`, `INVALID`, `WAITING`, `RUNNING`.

Example:
```bash
agy -p "<task prompt>" \
  --output-format json \
  --json-schema '{"type":"object","properties":{...},"required":[...]}' \
  --print-timeout 10m
# -> parse stdout JSON; require .status=="SUCCESS"; read .structured_output, .usage
```

### A.4 Common adapter contract

| Aspect | Claude Code | Codex | Antigravity |
|---|---|---|---|
| Structured flag | `--json-schema` + `--output-format json` | `--output-schema <file>` | `--json-schema` + `--output-format json` |
| Structured field | `structured_output` | schema-conformant stdout / `-o` file | `structured_output` |
| Text field | `result` | final stdout message | `response` |
| Usage/cost | `usage`, `total_cost_usd` | `usage` (in JSONL) | `usage` |
| Success check | exit code + envelope | exit code | `status == "SUCCESS"` |
| Diagnostics channel | stderr | stderr | stderr |
| Neutralize edits | no `--allowedTools`, scratch cwd | `--sandbox read-only` | soft-deny (default), scratch workspace |
| Auth | existing login (or `ANTHROPIC_API_KEY` w/ `--bare`) | saved auth or `CODEX_API_KEY` | cached creds (login once) |

Every adapter: separate stdout/stderr capture, parse the structured field first with a
delimiter-fenced-JSON + repair fallback, map `usage`/cost into the `ai_call` table, enforce
a timeout with process-tree kill, and normalize errors for the failover chain.

> **Applying the Claude-adapter riders to Codex/Antigravity (when those adapters land).**
> Two mechanisms built for the Claude Code adapter carry over — but only one is a drop-in:
>
> - **CLI version floor — reusable as-is.** `parse_cli_version` + `CliAdapter._minimum_version()`
>   + `check_availability()` live in the **base** class, so a Codex/Antigravity adapter only
>   overrides `_minimum_version()` (and `_version_argv()` if its `--version` format differs).
> - **Structured error classification — same idea, per-adapter mechanics.** The principle
>   (classify from a structured signal, keep the stderr heuristic as a fallback) holds, but the
>   signal differs and neither mirrors Claude's stream-json rewrite: **Antigravity** already
>   exposes a `status` field in its plain `--output-format json` envelope (no stream-json switch
>   needed; but its statuses are coarse — `ERROR`/`CANCELED`/… — not fine-grained auth-vs-rate-
>   limit); **Codex** surfaces errors via a `--json` JSONL `error` event with file-based
>   structured output (`-o out.json`). Event names/shapes differ across all three
>   (`system`/`assistant`/`result` vs `init`/`step_update`/`result` vs `thread.*`/`item.*`/
>   `error`), so field extraction stays per-adapter; a shared "scan NDJSON events" helper could
>   be lifted later. Tracked in [issue #15](https://github.com/Harikeshav-R/Atlas/issues/15).

---

*End of document.*
