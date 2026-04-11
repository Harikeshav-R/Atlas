# 05 — Subsystems: Profile, Discovery, Evaluation, Generation

> The canonical profile schema and the subsystems that turn job listings into evaluations and tailored documents. Load this for tasks on profile parsing, scrapers, the Evaluation Agent, or CV/cover letter generation.

**Prerequisites:** `docs/01-foundations.md`, `docs/02-agent-runtime.md`. **Companion docs:** `docs/03-persistence.md` for the schema of `listings`, `evaluations`, `application_assets`. `docs/07-delivery.md §5` for the PDF rendering pipeline used by the generation subsystem.

---

## 1. The canonical profile schema

The profile is the root of all personalization. Its schema has to be rich enough to power evaluation and CV generation without being so rigid that every user has to reshape their life to fit it.

### Top-level shape

A YAML document with these top-level keys:

- `schema_version` — integer, currently 1
- `personal` — name, pronouns, location, contact, links (LinkedIn, GitHub, portfolio), work authorization/visa status, willingness to relocate
- `summary` — a short self-description, optional
- `target` — what the user is looking for: titles, seniority levels, industries, remote model preferences, comp target (base, total, currency), deal-breakers, nice-to-haves
- `experience` — array of roles with company, title, start/end dates, location, employment type, summary, and bullets (each bullet has text and optional `evidence` tags used by the tailor agent)
- `education` — array of institutions with degree, field, dates, notable coursework
- `skills` — grouped by category (languages, frameworks, tools, domains), each with optional proficiency and years
- `projects` — array of projects with name, description, links, highlights
- `publications` — optional
- `certifications` — optional
- `languages` — spoken languages with proficiency
- `awards` — optional
- `volunteering` — optional
- `preferences` — things that matter for fit judgment but aren't traditional resume content: mission alignment preferences, team size preferences, pace preferences, management vs. IC preference, salary negotiation constraints
- `private_notes` — strictly internal context the user wants the agent to know but never to surface in a CV or cover letter (e.g., "I left company X on bad terms, don't use them as a reference"). Marked `private: true` and filtered from any external-facing content by default

### Design rules

- **Every bullet has evidence.** Bullets in experience are not just strings; they're objects with `text` and optional `skills`, `metrics`, `keywords`. The tailor agent uses these to decide which bullets to emphasize for a given JD and to know what keywords are legitimate to inject.
- **Dates are ranges, not points.** Use `start` and `end` (ISO date or `present`). Duration is derived.
- **Private fields are honored everywhere.** The `atlas-profile.read` tool has a `include_private` flag that defaults to false. Only the honesty verifier and the user's own viewing have access to private fields.
- **Schema version is required.** Migrations of the profile schema bump the version and run a migration against the stored YAML.

### The parser

The Profile Parser Agent is a small, constrained agent. Its job is to take raw extracted text from whatever format the user uploaded and produce a canonical YAML matching the schema. Its tools: `atlas-fs.read`, `atlas-profile.validate_schema`. Its process:

1. Read the raw text.
2. Produce a structured JSON matching the Zod schema.
3. Validate against the schema. If invalid, correct and retry.
4. Serialize to YAML.
5. Save via an IPC write back to main.

**Edge cases to handle:** scanned PDFs (LLM vision fallback), multi-column CVs (layout reconstruction), non-English CVs (language detection → prompt in the user's language), CVs with tables (extraction via the PDF parser's text flow).

The parser is the one place where "LLM does freeform extraction" is unavoidable. Everywhere else, structure is enforced.

---

## 2. Discovery subsystem

### Architecture

Discovery has two paths: a **fast path** for known platforms and an **agentic path** for generic sites.

**Fast path.** For Greenhouse, Ashby, Lever, Wellfound, each has a dedicated scraper adapter in `packages/scrapers/`. Each adapter exports a `list(source_config)` function that returns a list of `DiscoveredListing` objects by hitting the platform's public API or structured HTML endpoints. These adapters are deterministic, fast, and cheap. They're the default for sources configured with a known platform kind.

**Agentic path.** For sources configured as `generic_site`, the Discovery Agent is invoked with a small toolbox: `playwright.navigate`, `playwright.get_text`, `playwright.find_links`, `atlas-db.write_listing`. The agent navigates the page, identifies job listings, extracts them, and writes them. It's slower and more expensive but handles arbitrary career pages.

### Per-platform adapter notes

**Greenhouse.** Has a public JSON board API at `boards-api.greenhouse.io/v1/boards/{company}/jobs`. Use this. Returns structured listings directly. Cheapest path.

**Ashby.** Public API via their job board embed endpoint. Structured JSON.

**Lever.** Public API at `api.lever.co/v0/postings/{company}?mode=json`. Structured.

**Wellfound** (AngelList Talent). No clean public API. Scraping required, respect their ToS. Agentic path is safer here.

**Workable, SmartRecruiters.** Each has patterns. Use their public board endpoints where available.

Adapters all implement the same interface: `list(config)` returning `DiscoveredListing[]`, `fetch(url)` returning a full `Listing` with description, and `canonicalize(url)` returning the canonical URL for dedup.

### RSS ingestion

The RSS source kind uses `rss-parser` to pull feed items on schedule. Each item is treated as a candidate listing; if the item has a direct link to a JD, it's canonicalized and processed. If it's a newsletter with multiple jobs in one post, a small agent extracts the individual listings from the post content.

### Deduplication

A new listing goes through a three-stage dedup check:

1. **URL canonicalization.** Strip tracking params, normalize scheme and host, drop trailing slashes. If the canonical URL matches an existing listing, merge as a new source reference on that listing.
2. **Title + company match.** Normalize whitespace and punctuation, lowercase. If (normalized company, normalized title) matches within a time window (default 30 days), merge.
3. **Semantic similarity (optional).** If the user has embeddings enabled, compare JD text embeddings against recent listings. High similarity → prompt user to confirm merge, or auto-merge above a threshold.

Each merge records the source references so the listing tracks all the places it was seen.

### Source health

Each source run updates `last_run_at`, `last_success_at`, `last_error`, and `consecutive_failures`. A source with 3+ consecutive failures is marked degraded and surfaced on the Source Health dashboard. 10+ failures auto-disables the source with a notification. The user can re-enable from the dashboard.

For the scheduler that drives discovery runs, see `docs/06-subsystems-application-stories-negotiation.md §4`.

---

## 3. Evaluation subsystem

### Flow

Every newly-discovered listing goes through **triage** first. Triage is a cheap agent (single model call, minimal tools) that produces a numeric score and a go/no-go decision. Listings scoring below a threshold (default 4/10) are archived without deep evaluation; listings scoring at or above are queued for deep evaluation.

**Deep evaluation** is the full 6-block agent run. The Evaluation Agent has a larger toolbox (`atlas-db.*`, `atlas-web.*`, optionally `playwright.get_text` for reading the live page), a higher budget, and a stronger model.

For the 6-block structure and 10-dimension scoring, see `product-plan.md`.

### Output validation

Both triage and deep evaluation produce structured output validated by Zod. The Evaluation Agent's `outputSchema` covers all 6 blocks plus the scorecard. If the output is invalid after retries, the run fails and the listing is marked `evaluation_failed` for manual review.

### Re-evaluation

When the profile changes, a batch re-evaluation is offered. The user sees how many listings would be re-evaluated and the estimated cost before confirming. **Re-evaluations write new `evaluations` rows (they don't overwrite)** so diffs are preserved.

### Comp research

Block 4 (Comp Research) is where the agent uses `atlas-web.search` and `atlas-web.fetch` most heavily. Good queries include the company name + "salary" + role, Levels.fyi for tech, Glassdoor where available, and public funding data. The agent is prompted to cite sources for any specific number it reports.

---

## 4. Generation subsystem

### The pipeline

CV and cover letter generation share a pipeline:

1. **Evaluation context is loaded.** The latest evaluation for the listing is passed to the generator.
2. **The CV Tailor Agent or Cover Letter Agent runs.** Its job is structured: produce a JSON output matching the template's expected context.
3. **Honesty verification runs as a separate agent.** The verifier compares the generated content against the canonical profile and flags unsupported claims.
4. **The user reviews flagged items if any.** Clean runs proceed automatically; flagged runs surface for user decision.
5. **PDF rendering.** The validated context is passed to `atlas-fs.render_pdf` with the chosen template ID. See `docs/07-delivery.md §5` for the rendering pipeline.
6. **Asset is persisted.** A row in `application_assets` records the path and the agent runs involved.

### Template system

Templates live in `packages/pdf-templates/`. Each template is a directory containing:
- `template.html` — Mustache template (no embedded logic allowed in templates)
- `styles.css` — print-oriented CSS, paged via `@page` rules
- `fonts/` — bundled font files
- `manifest.json` — template metadata (name, description, expected context schema)

The expected context schema is a Zod schema the generator must match. **This is the contract between the generator agent and the template:** the agent outputs a JSON structure, the schema validates it, and the template consumes it.

**Templates never do logic.** All computation happens in the generator agent. Templates just render.

### Keyword injection rules

The CV Tailor Agent's system prompt includes explicit rules:
- Only reorder, re-emphasize, and reword the user's existing content.
- Keywords from the JD may be injected only if they correspond to skills/experience the user actually has in their profile.
- No claims may be added that are not supported by bullets in the profile.
- No dates, titles, or metrics may be changed.
- Quantitative claims must come verbatim from the profile (the generator can emphasize an existing metric but cannot invent one).

The Honesty Verifier Agent enforces these rules by running a checklist against the generated output and the profile, flagging any violation.

### Cover letter specifics

Cover letters have stricter personalization requirements than CVs. The Cover Letter Agent is expected to reference specific company details from Block 5 (Personalization) of the evaluation and to use at least one Story Bank entry when relevant. The output schema requires `opening_hook`, `relevance_paragraphs`, `company_specific_reference`, `closing`, each with minimum lengths.

For the Story Bank itself and how stories are surfaced to this agent, see `docs/06-subsystems-application-stories-negotiation.md §2`.
