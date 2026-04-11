# 03 — Persistence

> Database schema, migrations, file system layout, secrets management. Load this for any task touching the database, file storage, or credentials.

**Prerequisites:** `docs/01-foundations.md`. **Companion docs:** `docs/02-agent-runtime.md` for the runs/trace_events/approvals tables in their broader context, `docs/04-app-shell.md §4` for the worker pool's "no DB access" rule.

---

## 1. Database schema

Full schema, table by table. This is what Drizzle schema files will encode. Types are conceptual (SQLite has a narrow native type set — TEXT, INTEGER, REAL, BLOB — so "uuid" really means TEXT and "timestamp" means TEXT in ISO format).

### Conventions

- Every table has a `created_at` and `updated_at` (ISO UTC).
- Every table has a primary key ending in `_id` with a type-specific ULID prefix.
- Foreign keys use `ON DELETE` policies explicitly — never the default.
- Booleans are INTEGER 0/1.
- JSON blobs use SQLite's `JSON1` functions for indexing and are validated against Zod schemas at write time.
- Indexes are defined alongside tables — if a column is queried, it's indexed.

### Tables

**`profiles`**
- `profile_id` (PK)
- `yaml_blob` — the full canonical YAML
- `parsed_json` — the parsed JSON of the profile for indexed querying
- `version` — monotonic integer, incremented on every save
- `schema_version` — the YAML schema version
- `created_at`, `updated_at`

Only one row in practice (single user per install), but the table is designed to support multiple versions for history and for re-evaluation diffs.

**`preferences`**
- `preferences_id` (PK)
- `profile_id` (FK)
- `scoring_weights_json` — the 10-dimension weights
- `grade_thresholds_json` — A/B/C/D/F cutoffs
- `model_routing_json` — stage-to-model mapping
- `budgets_json` — global monthly budget, per-agent budget overrides
- `notification_prefs_json`
- `updated_at`

**`sources`**
- `source_id` (PK)
- `kind` — `ats_greenhouse`, `ats_ashby`, `ats_lever`, `ats_wellfound`, `rss`, `generic_site`, `linkedin`
- `name` — human-readable
- `config_json` — kind-specific config (company slug, feed URL, search query, etc.)
- `schedule_cron` — cron expression for how often to scrape
- `enabled` (boolean)
- `last_run_at`, `last_success_at`, `last_error`, `consecutive_failures`
- `created_at`, `updated_at`

Index on (`enabled`, `last_run_at`) for the scheduler's query.

**`listings`**
- `listing_id` (PK)
- `canonical_url` — the normalized URL, used as a dedup key (unique index)
- `company_name`
- `role_title`
- `location`
- `remote_model` — `remote`, `hybrid`, `onsite`, `unknown`
- `description_markdown` — the extracted JD as markdown
- `description_hash` — hash of description for change detection
- `first_seen_at`, `last_seen_at`, `removed_at` (nullable)
- `status` — `active`, `removed`

Indexes on `canonical_url` (unique), `company_name`, `first_seen_at`, `status`.

**`listing_sources`** (M:N between listings and sources)
- `listing_id`, `source_id` (composite PK)
- `first_seen_at`, `last_seen_at`

**`listing_snapshots`**
- `snapshot_id` (PK)
- `listing_id` (FK)
- `captured_at`
- `raw_html_path` — path under `{userData}/snapshots/` (not stored inline)
- `extracted_text`
- `content_hash`

The path field points to a file on disk; large HTML bodies do not live in SQLite.

**`evaluations`**
- `evaluation_id` (PK)
- `listing_id` (FK)
- `profile_version` — which version of the profile this was evaluated against
- `agent_run_id` (FK to runs)
- `grade` — letter grade
- `score` — numeric 0–10
- `six_blocks_json` — structured 6-block output
- `summary_text` — the "why this grade" paragraph
- `created_at`

Unique index on (`listing_id`, `profile_version`) — one evaluation per listing per profile version.

**`scorecards`**
- `scorecard_id` (PK)
- `evaluation_id` (FK, unique)
- `dimensions_json` — array of 10 dimension objects with score, justification, weight
- `weighted_total` — numeric

**`applications`**
- `application_id` (PK)
- `listing_id` (FK)
- `status` — enum (see state machine in `docs/08-reference.md §2`)
- `applied_at` (nullable)
- `last_status_change_at`
- `notes`
- `created_at`, `updated_at`

**`application_assets`**
- `asset_id` (PK)
- `application_id` (FK)
- `kind` — `tailored_cv`, `cover_letter`, `answers`
- `path` — file path under `{userData}/applications/{application_id}/`
- `agent_run_id` (FK to runs)
- `honesty_verified` (boolean)
- `honesty_verifier_run_id` (FK to runs, nullable)
- `created_at`

**`offers`**
- `offer_id` (PK)
- `application_id` (FK, unique)
- `base_amount`, `base_currency`
- `bonus_json`, `equity_json`, `signon_json`
- `start_date`
- `deadline`
- `status` — `pending`, `counter_offered`, `accepted`, `rejected`, `withdrawn`
- `counter_offers_json` — array of counter-offer history
- `created_at`, `updated_at`

**`stories`**
- `story_id` (PK)
- `title`
- `situation`, `task`, `action`, `result`, `reflection` (all text)
- `themes_json` — array of theme tags
- `source` — `interactive_intake`, `cv_extraction`, `evaluation_extraction`, `manual`
- `created_at`, `updated_at`

**`story_links`**
- `story_id`, `consumer_kind` (`evaluation` | `cover_letter` | `interview_prep`), `consumer_id` (composite PK)
- `created_at`

**`runs`**
- `run_id` (PK)
- `parent_run_id` (FK, nullable)
- `agent_name`
- `mode` — `normal`, `dry-run`, `eval`
- `input_hash` — hash of input for fixture matching
- `input_json` — run input (consider offloading to blob if large)
- `model_id`
- `fallback_used` (boolean)
- `started_at`, `ended_at`
- `status` — `queued`, `running`, `succeeded`, `failed`, `killed`, `budget_exhausted`, `timeout`
- `result_json` — final result or error
- `total_cost_usd`
- `total_tokens`
- `iterations_used`
- `eval_suite_id` (nullable)

Indexes on `agent_name`, `status`, `started_at`.

**`trace_events`**
- `event_id` (PK)
- `run_id` (FK)
- `parent_event_id` (FK, nullable)
- `step_index` (integer, monotonic within run)
- `timestamp`
- `type` — see `docs/02-agent-runtime.md §10` for the enum
- `actor`
- `payload_json` (small payloads only; large payloads offloaded to blob store)
- `cost_usd` (nullable)
- `duration_ms` (nullable)

Indexes on `run_id`, `(run_id, step_index)`, `type`.

**`approvals`**
- `approval_id` (PK)
- `run_id` (FK)
- `scope` — the structured scope string (see `docs/02-agent-runtime.md §11`)
- `title`, `description`
- `screenshot_path` (nullable)
- `options_json` — available choices
- `status` — `pending`, `granted`, `denied`, `timed_out`
- `user_response_json` (nullable)
- `requested_at`, `responded_at` (nullable)
- `timeout_at`

Indexes on `status`, `run_id`.

**`costs`**
- `cost_id` (PK)
- `run_id` (FK)
- `event_id` (FK to trace_events)
- `model_id`
- `prompt_tokens`, `output_tokens`
- `cost_usd`
- `timestamp`

Indexes on `run_id`, `timestamp`, `model_id`.

**`model_pricing`**
- `model_id` (PK)
- `prompt_token_cost_usd_per_million`
- `output_token_cost_usd_per_million`
- `effective_from`, `effective_to` (nullable)

**`audit_log`**
- `log_id` (PK)
- `timestamp`
- `actor` — `user`, `system`, `agent:{name}`
- `action` — free-form action string
- `target_kind`, `target_id` — what was acted on
- `details_json`

A broader log than `trace_events`; captures user actions like "imported profile," "changed weights," "enabled YOLO mode for batch X." Searchable from the UI.

---

## 2. Migrations

Drizzle generates SQL migration files. Migrations are checked into git in `packages/db/migrations/`. On app startup, the app runs any pending migrations automatically against the user's DB. Migration runs are recorded in a `migrations` table that Drizzle manages.

**Rules:**
- Migrations are **forward-only**. No down migrations. If a migration is wrong, write a new one that corrects it.
- Migrations must be **idempotent** where possible. Destructive migrations (dropping columns, renaming tables) are done in phases: add new column → backfill → switch reads → switch writes → drop old in a later release.
- **Never delete user data in a migration.** If a feature is removed, leave its tables in place and stop writing to them. A later release can drop them after users have had time to update.
- **Test migrations on a copy.** Before running a migration on the user's live DB, the app makes a backup copy of the DB file to `{userData}/backups/pre-migration-{version}.sqlite`.

---

## 3. File system layout

All of Atlas's on-disk state lives under Electron's `userData` directory for the current user:

```
{userData}/
  atlas.sqlite                  Main SQLite DB
  atlas.sqlite-wal              WAL file (don't touch)
  atlas.sqlite-shm              Shared memory file (don't touch)
  logs/
    atlas.log                   Current log
    atlas-2026-04-08.log        Rotated logs
  snapshots/
    {listing_id}/
      {captured_at}.html        Raw HTML snapshots
  applications/
    {application_id}/
      tailored-cv.pdf
      cover-letter.pdf
      answers.json
      screenshots/
        submit-preview.png
  traces/
    {run_id}/
      {event_id}.json           Large payloads referenced from trace_events
  profile/
    current.yaml                The canonical profile YAML (also in DB)
    imports/
      {import_id}/
        original.pdf            The user's original upload
        extracted.txt
  templates/                    Read-only, bundled with the app
  backups/
    pre-migration-{version}.sqlite
    manual-{timestamp}.zip      User-initiated full backups
  browser-profiles/             Playwright persistent contexts
    {portal}/
  secrets/                      (not really files — keytar handles storage)
```

**Permissions:** the app sets restrictive permissions on `{userData}` at first launch (user-only read/write). Sensitive subdirectories (`profile/`, `applications/`, `traces/`) are not opened to any process other than Atlas.

**Disk usage management:** a periodic health check computes disk usage under `{userData}` and warns if it exceeds a threshold (default 2GB). Snapshots and traces are the biggest contributors; both have configurable retention policies.

---

## 4. Secrets and credentials

All secrets go through `keytar`. Secrets Atlas may store:
- LLM provider API keys (Anthropic, OpenAI, OpenRouter)
- Portal login credentials (if the user enables auto-login features)
- Email digest SMTP credentials (if enabled)

**Key naming convention:** `atlas/{category}/{identifier}`. E.g., `atlas/llm-provider/anthropic`, `atlas/portal/greenhouse/company-x`. This keeps Atlas's secrets namespaced in the OS keychain.

**In-memory handling:**
- Secrets are loaded from the keychain only when needed, never kept in a long-lived global.
- Portal credentials are loaded into a scoped session object at the start of a submission run and wiped at the end via explicit `Buffer.fill(0)` on any buffer containing them.
- **Secrets never appear in logs, traces, or audit events.** A scrubbing middleware at the log layer checks for known patterns (anything starting with `sk-`, `sk-ant-`, `Bearer `) and redacts them even if accidentally passed through.

**User-facing controls:** Settings has a dedicated Secrets tab listing all stored secrets by name (not value), with a "delete" button per secret and a "delete all Atlas secrets" nuclear option.
