# 04 — The App Shell

> Electron security hardening, the IPC layer, the worker pool, and the renderer architecture. Load this for any task touching Electron config, IPC channels, workers, or the UI.

**Prerequisites:** `docs/01-foundations.md`. **Companion docs:** `docs/02-agent-runtime.md` for what runs inside workers (agents), `docs/03-persistence.md` for the "workers never touch SQLite" rule.

---

## 1. Electron security hardening

**All defaults are wrong.** The correct configuration:

- `contextIsolation: true`
- `nodeIntegration: false`
- `sandbox: true`
- `webSecurity: true`
- `allowRunningInsecureContent: false`
- `experimentalFeatures: false`
- Content-Security-Policy header on all renderer HTML: `default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: file:; connect-src 'self'; font-src 'self'; object-src 'none'; frame-ancestors 'none'; base-uri 'none'`
- The renderer **never loads remote content**. No `<iframe>` pointing outside the app. No `<img src="https://...">`. All assets are bundled or loaded via custom protocols that resolve to local files.
- `app.on('web-contents-created')` handler that blocks all navigation and `new-window` events. The only navigation permitted is between Atlas's own routes.
- `session.setPermissionRequestHandler` that denies all permission requests by default (camera, microphone, geolocation, notifications-from-renderer).
- Renderer has no access to the file system, `require`, or any Node globals. The preload script exposes only the IPC surface.

**Never disable any of these "just for testing." Not even once.**

---

## 2. The IPC layer

### Why it matters

The renderer is the untrusted part of the app from a security perspective — if a malicious page ever got loaded, Node access would mean game over. The IPC surface is the only way the renderer affects the world. **It must be tight.**

### Design

A single preload script exports a typed API on `window.atlas` via `contextBridge.exposeInMainWorld`. The API is organized into namespaces: `window.atlas.profile.*`, `window.atlas.runs.*`, `window.atlas.approvals.*`, etc.

Under the hood, each exposed method sends an `ipcRenderer.invoke(channel, payload)` to a registered handler in main. The channel name is `namespace.verb`. **Payloads and responses are validated on both sides** with the shared Zod schemas from `@atlas/schemas`.

### Channels

Channels are grouped by subsystem. Representative list:

- `profile.import(file)` — main parses, returns canonical YAML or errors
- `profile.get()` — returns current profile
- `profile.update(yaml)` — validates and saves
- `sources.list()`, `sources.create`, `sources.update`, `sources.delete`
- `runs.start(agent_name, input)` — queues a run, returns run ID
- `runs.list(filter)` — returns runs matching filter
- `runs.get(run_id)` — returns run details with trace
- `runs.kill(run_id)` — sets kill flag
- `approvals.list()` — returns pending approvals
- `approvals.respond(approval_id, response)` — submits a decision
- `listings.list(filter)`, `listings.get(listing_id)`
- `applications.list(filter)`, `applications.shortlist(listing_id)`
- `settings.get()`, `settings.update(patch)`
- `costs.summary(period)` — returns cost dashboard data
- `audit_log.query(filter)` — returns audit events

### Events

In addition to invoke/response, the main process pushes events to the renderer via `webContents.send`. The renderer subscribes via a typed API. Events:

- `runs.updated(run_id)` — a run's status changed
- `approvals.new(approval_id)` — a new approval is pending
- `listings.new(count)` — new listings discovered
- `notifications.desktop(payload)` — used when the main process wants the renderer to surface an in-app notification too

### Validation

Every incoming payload is validated. Every outgoing response is validated. Validation failures are logged and return structured errors. The renderer never trusts main responses blindly either — a bug in main shouldn't be able to crash the renderer.

### Error propagation

Handlers in main wrap their logic in a try/catch that converts any thrown error into a structured `AtlasError` response. The renderer's IPC wrapper transforms error responses into thrown exceptions on the renderer side so components can use try/catch naturally.

---

## 3. Worker pool

Heavy work (parallel evaluations, scraping batches, PDF generation under load) runs in worker processes spawned via Electron's `utilityProcess`.

### Design

The main process hosts a worker pool manager. The manager maintains a pool of N worker processes (configurable, default 4). Each worker is a script that loads the harness, the model router, and whatever subsystems it needs, then listens for job messages on its IPC channel.

Jobs have a type (`agent_run`, `scrape`, `pdf_render`), a payload, and a correlation ID. The manager dispatches jobs by round-robin or least-busy. Workers report progress and results back over IPC.

### The DB rule

**Workers do not open the SQLite database.** `better-sqlite3` is synchronous and not process-safe. Workers get their data by requesting it from the main process via RPC-over-IPC and report results the same way. This sounds like a bottleneck but isn't in practice — the work inside a worker (LLM calls, scraping) is dramatically slower than the marshalling cost.

### Failure handling

A crashed worker is detected by the manager and replaced. The in-flight job is marked failed and (for idempotent operations) retried on a different worker. The crash is logged. Repeat crashes on the same job indicate a bug; the manager will stop retrying after a threshold.

### Concurrency control

Beyond the worker count itself, `p-limit` is used to cap concurrency per stage within the pool. A user with 4 workers running Evaluation Agents might have cost concurrency capped at 2 if they've set a low budget — this is a separate mechanism from the worker pool size.

---

## 4. Renderer architecture

### Stack

- **React 18** with function components and hooks. No class components. No Redux/MobX.
- **TanStack Router** for type-safe routing. File-based routes live in `apps/desktop/renderer/src/routes/`.
- **TanStack Query** wraps IPC calls that return server-like data (runs, listings, approvals). It provides caching, background refetch, and stale-while-revalidate out of the box, which matches how users will interact with the app.
- **Zustand** for small global UI state (selected filters, modal open state, kill-switch UI flag). Not for server data — that's TanStack Query's job.
- **Tailwind CSS** and **shadcn/ui** for every component. shadcn components are copied into `apps/desktop/renderer/src/components/ui/`, owned by the project, and customized.
- **Lucide** for icons.
- **Space Grotesk** and **DM Sans** as the UI typefaces, loaded via @font-face from bundled woff2 files (never from Google Fonts — no remote fetches).

### Screens

- **Dashboard** — the pipeline view with filters, sort, bulk actions.
- **Listing detail** — a single listing with its evaluation, generated assets, and apply button.
- **Profile** — canonical profile editor with form UI over YAML.
- **Sources** — CRUD for scraping sources.
- **Approvals** — the Approval Queue (see `docs/02-agent-runtime.md §11` and `docs/06-subsystems-application-stories-negotiation.md §1`).
- **Runs** — the Trace Viewer (see `docs/02-agent-runtime.md §10`).
- **Cost** — budget and spend dashboard.
- **Settings** — provider keys, model routing, budgets, notification prefs.
- **Audit Log** — searchable history of user and system actions.
- **Story Bank** — story browser and rehearsal mode.
- **Offers** — active offers with negotiation scripts.

### State patterns

- **Server state** (anything that comes from main) → TanStack Query with a consistent query key convention: `[namespace, verb, ...args]`.
- **URL state** (filters, sort) → TanStack Router search params. This makes every view bookmarkable and the browser's forward/back work.
- **Local UI state** (open/closed, selected item) → `useState`.
- **Cross-component UI state** (global modal, kill-switch activity indicator) → Zustand.

### Accessibility

**Non-negotiable baseline:**
- All interactive elements have keyboard focus and visible focus rings.
- Tab order is logical.
- Color is never the only signal (always paired with text or iconography).
- All images have alt text (or explicit empty alt for decorative images).
- Contrast ratios meet WCAG AA.
- The Approval Queue is keyboard-navigable without a mouse.
- Screen reader support via proper ARIA roles on custom components.

**This is not a phase 5 feature.** shadcn/ui's Radix primitives give you most of this for free; don't break it.

### Browser storage prohibition

**Never use `localStorage`, `sessionStorage`, `IndexedDB`, or any browser storage API in the renderer.** State goes through IPC to main, which persists in SQLite. This is enforced by code review, not the type system — be vigilant.
