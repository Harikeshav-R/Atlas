# 06 — Subsystems: Application, Stories, Negotiation, Scheduler, Notifications

> The application engine (the highest-stakes subsystem), the Story Bank, negotiation, the scheduler/run queue, and notifications. Load this for tasks on auto-apply, the Application Agent, the Story Bank, negotiation, scheduling, or notifications.

**Prerequisites:** `docs/01-foundations.md`, `docs/02-agent-runtime.md`. **Companion docs:** `docs/02-agent-runtime.md §11` for the approval flow (load this for any work touching the Application Agent), `docs/05-subsystems-discovery-evaluation-generation.md` for the generation pipeline whose output the Application Agent consumes.

---

## 1. Application subsystem

**This is the most complex subsystem in Atlas and the one where failures are most visible to the user.** Read this section carefully before touching the Application Agent or any submission tool. Then read `docs/02-agent-runtime.md §11` and `§12` before writing any code.

### The Application Agent's task

Given an application ID (pointing to a listing with a generated CV and cover letter), navigate to the listing's apply URL, fill the form fields from the profile, answer any open questions using the profile and Story Bank, attach the generated CV and cover letter, request user approval with a screenshot summary, and (on approval) submit.

### Portal adapters

While the agent is agentic, **per-portal adapters provide scaffolding to make the agent's job easier**. An adapter for Greenhouse encodes what Greenhouse forms look like: which field names correspond to which profile fields, where the submit button lives, what CAPTCHA patterns to watch for. The adapter exposes this as a set of hints the agent consumes at the start of a run — not as hard-coded automation, but as a head start.

The adapter hint shape:
- `field_mappings` — selectors or label patterns to profile field names
- `file_upload_mappings` — which upload control takes the CV vs. cover letter
- `known_questions` — common open-question patterns and suggested profile fields to draw from
- `submit_selector` — the submit button
- `captcha_patterns` — selectors that indicate a captcha is present
- `success_indicators` — what the page looks like after successful submission

Adapters exist for Greenhouse, Ashby, Lever initially. Other portals get the generic agentic path. **Adapter hints are loaded into the agent's initial context as a structured note, inside untrusted-content markers** where appropriate.

### Form-filling flow

1. **Context load.** The agent is given the application ID, loads the application assets and the canonical profile via tools.
2. **Navigate.** `playwright.navigate` to the listing's apply URL, using a persistent browser context for the portal (cookies preserved from any prior runs).
3. **Detect form.** The agent uses `playwright.get_text` and DOM inspection tools to identify form fields and their labels.
4. **Fill obvious fields.** Name, email, phone, location, LinkedIn, portfolio — direct mapping from profile.
5. **Fill structured fields.** Education, experience, eligible-to-work, visa sponsorship, etc. — more mapping.
6. **Fill open questions.** "Why do you want to work here?" — the agent uses `atlas-profile.query_stories` and the evaluation's Block 5 to compose an answer. **Answers are always grounded in the profile, never invented.**
7. **Attach files.** Upload the tailored CV and cover letter via `playwright.upload_file` on the identified file inputs.
8. **Screenshot.** `playwright.screenshot` captures the fully-filled form.
9. **Request approval.** `atlas-user.request_approval` with the screenshot, a summary of what was filled, and scope `submit:{portal}:{company}:{req_id}`.
10. **On approval: submit.** `playwright.click` on the submit button. The submit-gate wrapper permits this because of the matching approval.
11. **Confirm success.** Verify the success page/message. If not confirmed, log and request user attention.
12. **Record.** Write to `applications` and `application_assets` with the final status.

### Error handling

- **CAPTCHA detected.** The agent stops and calls `atlas-user.request_approval` with a description asking the user to solve the CAPTCHA manually in the open browser window. Once the user clicks "I solved it," the agent resumes.
- **MFA required.** Same pattern.
- **Field doesn't match anything in profile.** The agent calls `atlas-user.ask` with the field label and context, requests a value, and proceeds.
- **Portal error.** The agent logs the error, captures a screenshot, marks the application as `failed:portal_error`, and terminates. The user sees it in the Approval Queue as a failed attempt.
- **Unexpected page.** The agent terminates rather than trying to recover blindly. **A wrong page on a submission is far more dangerous than a failed run.**

### Rate limiting

Per-portal rate limits are enforced at the tool level: `playwright.navigate` and `playwright.submit_form` check a rate-limit table before proceeding and sleep or fail if over the limit. Default: 5 submissions per portal per hour, configurable in Settings.

### Dry-run mode

In dry-run mode, the entire flow runs except the final submit click is replaced with a no-op that logs "would have submitted." The agent still requests approval (so the user gets to see the UX) but the submission itself is simulated. The run is marked `mode: dry-run` in the trace.

### YOLO mode

In YOLO mode, the approval step still happens but the approval is auto-granted after a short visible delay (default 10 seconds, during which the user can intervene via a "cancel" button on the desktop notification). The trace records the auto-approval with a `note` event. Kill switch still works.

**YOLO mode has strict scope:** it's enabled per batch, with a user-set maximum batch size, and auto-disables after the batch completes. There is no "leave YOLO on globally" option. This is deliberate — no one should wake up to 47 accidental submissions.

---

## 2. Story Bank subsystem

### First-run interactive intake

On first launch after profile import, Atlas offers (not forces) an interactive Story Bank intake. The user accepts, and the Story Bank Interview Agent starts a conversational session. The agent's tools: `atlas-profile.read`, `atlas-user.ask`, `atlas-db.write_story`.

The agent's flow:
1. Reviews the user's experience from the profile.
2. Identifies 5–10 candidate experiences that could be developed into STAR+R stories (significant projects, leadership moments, failures, cross-functional wins).
3. For each, asks follow-up questions to draw out Situation, Task, Action, Result, and Reflection.
4. Writes each completed story via `atlas-db.write_story` with appropriate theme tags.

The session is long-running (can take 20–40 minutes of user time) but can be paused and resumed. Progress is persisted so a partial intake isn't lost on quit.

### Passive story accumulation

After the initial intake, the system looks for story-worthy content in profile updates and past evaluations. When the CV Tailor Agent identifies a bullet that could be a story but isn't yet in the bank, it emits a suggestion via `atlas-db.write_story_candidate`. Candidates surface in the Story Bank UI for the user to convert into full stories on their own time.

### On-demand gap-filling

When the Evaluation Agent's Block 6 identifies an interview question for which no matching story exists, it emits a story request. The user sees a notification: "The upcoming [company] interview is likely to ask about X. You don't have a story for this yet. Start a 5-minute intake?" On accept, the Interview Agent launches a narrow session targeted at that theme.

### Story retrieval

The `atlas-stories.query(theme, question)` tool returns stories scored for relevance to a specific question. Scoring is done by a small LLM call inside the tool. This is the main consumer during cover letter generation and interview prep.

---

## 3. Negotiation subsystem

### Offer entity

Offers are first-class. When a user receives one, they enter it manually (copy-paste the offer details into a structured form). The form produces an `offers` row with base, bonus, equity, signon, start date, deadline, and any other structured fields. See `docs/03-persistence.md §1` for the schema.

### Script generation

The Negotiation Agent generates scripts specific to the offer. Its tools: `atlas-db.read_offer`, `atlas-db.read_listing`, `atlas-db.read_evaluation`, `atlas-profile.read`, `atlas-web.search` (for market data), `atlas-user.ask` (for leverage clarification — "do you have a competing offer?").

Output: a markdown document with sections for opening, anchor, counter-offer, fallback positions, and closing. The script is personalized to the specific offer, the user's leverage, the company's likely flexibility (based on stage and comp data), and the user's preferences from the profile.

### Counter-offer simulator

A separate, lighter mode: the user tweaks parameters ("what if I ask for X% more base?") and the agent models likely outcomes given what it knows about the company and role. **This is explicitly framed as exploration, not prediction.**

### Deadline tracking

Offers with deadlines generate reminders. The scheduler checks daily and notifies when an offer is within 48 hours of its deadline.

---

## 4. Scheduler and run queue

### Design

The scheduler is a single module in the main process with a tick loop (every 30 seconds by default). On each tick:

1. Query `sources` for due discovery runs.
2. Query scheduled maintenance tasks (health checks, trace cleanup, offer deadline checks).
3. Query `runs` for queued work.
4. For each due item, check concurrency limits and global budget.
5. Dispatch to the worker pool or run in-process.

### Run queue

Runs are created in `queued` status by IPC calls from the renderer or by the scheduler itself. The queue is the `runs` table filtered to `status = 'queued'`. A FIFO order with optional priority field. The worker pool picks up queued runs in priority order.

### Concurrency caps

- **Global:** max N concurrent runs total (default 4).
- **Per agent:** max N concurrent runs of the same agent (default 2).
- **Per stage:** max N concurrent runs using the same model stage (prevents burning rate limits).
- **Per portal:** max 1 concurrent Application Agent run per portal (prevents race conditions in browser contexts).

All caps are enforced by `p-limit` instances keyed by scope.

### Persistent cron

Users configure source schedules as cron expressions. The scheduler uses `cron-parser` to compute the next due time for each source. Cron state is persistent — an app restart doesn't miss due runs.

---

## 5. Desktop notifications and email digest

### Desktop notifications

Electron's native `Notification` API on macOS uses the system notification center. Atlas uses it for:
- New A-grade listings
- Pending approvals (with action buttons: Approve, Deny, View)
- Run failures
- Offer deadlines approaching
- Budget alerts (80% of monthly budget, 100%)
- YOLO mode active (persistent indicator)

Notification preferences are per category in Settings. The user can mute anything.

### Email digest

The email digest is an opt-in daily or weekly summary. Users configure SMTP credentials (stored in keytar — see `docs/03-persistence.md §4`). The digest template is rendered by the same PDF pipeline as CVs (HTML → HTML email via a different template set). Content:
- New listings by grade
- Pipeline movements
- Pending approvals (with deep links to atlas:// URLs that open the app)
- Cost summary

For users who don't want SMTP, an alternative is "write digest HTML to a file and open it in the default browser on a schedule." Still useful, no email setup required.
