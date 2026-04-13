# 07 — Delivery

> Testing strategy, build/packaging/release, observability and debugging, development workflow, the PDF rendering pipeline, first-run experience, and the operational runbook. Load this for tasks on tests, CI, builds, releases, PDF templates, onboarding, or debugging.

**Prerequisites:** `docs/01-foundations.md`. **Companion docs:** `docs/02-agent-runtime.md §13` for the agent eval framework details, `docs/03-persistence.md` for migration rules, `docs/04-app-shell.md` for Electron security expectations the build must preserve.

---

## 1. Testing strategy

### Test pyramid

- **Unit tests (Vitest)** for pure functions, schemas, utility modules, tool implementations (with mocked DB). Target >80% coverage on `packages/shared`, `packages/schemas`, `packages/db` query helpers, and tool implementation files.
- **Integration tests (Vitest)** for MCP servers in-process, scraper adapters against saved HTML fixtures, the harness loop with a fake Model Router, and end-to-end IPC handlers with a test SQLite DB.
- **Agent eval tests** (the eval runner, see `docs/02-agent-runtime.md §13`) for actual agent behavior.
- **End-to-end tests (Playwright Test)** for the Electron UI: launch the app, import a profile, run an evaluation against a mocked LLM provider, check the UI updates. **These run against a mock provider, not real Claude.**
- **Manual smoke tests** before each release, checklist-driven.

### What to mock and what not to

- **LLM calls** — always mocked in unit and integration tests. A fake Model Router returns scripted responses.
- **Network (web search, fetch)** — always mocked with fixtures.
- **Playwright** — mocked for unit tests; runs against real saved HTML fixtures for integration; runs against a headless browser against a local test server for e2e.
- **SQLite** — never mocked. Tests use a real `better-sqlite3` against an in-memory or temp-file DB. The DB is too central to mock.
- **Filesystem** — never mocked. Tests use a temp directory.
- **Time** — mocked via the shared `now()` function being injectable.
- **Keytar** — mocked in tests (the real keychain is noisy and cross-test pollution is a pain).

### Fixtures

- **JD fixtures** live in `packages/scrapers/test-fixtures/` as saved HTML files representing real listings from each supported portal. These are used by adapter tests and eval fixtures.
- **Profile fixtures** live in `packages/schemas/test-fixtures/profiles/` — sample profiles of varying shape and completeness.
- **LLM response fixtures** live alongside the tests that use them, as JSON files named after the test.

**Never commit real scraped HTML containing a real person's name, email, or resume as a test fixture.** Use synthetic data or scrubbed fixtures.

### CI

GitHub Actions runs unit and integration tests on every push. Full e2e tests on PRs touching renderer or IPC code. Agent eval smoke tests on PRs touching agents or prompts. Full eval suites on release branches.

---

## 2. Build, packaging, and release

### Development build

`pnpm dev` runs `electron-vite dev` which starts both the main and renderer in watch mode. HMR for the renderer, auto-reload for main. The dev build loads from `http://localhost:5173` for the renderer and runs main from source.

### Production build

`pnpm build` runs `electron-vite build` which produces:
- `apps/desktop/out/main/` — compiled main process
- `apps/desktop/out/preload/` — compiled preload script
- `apps/desktop/out/renderer/` — compiled renderer assets

Then `electron-builder` bundles these with an Electron runtime into platform-specific installers.

### electron-builder config

Key settings:
- `appId: com.atlas-project.desktop` (replace with real)
- `productName: Atlas`
- `asar: true` with `asarUnpack` for native modules (`better-sqlite3`, `keytar`)
- `files` explicitly listed (no wildcards that might include junk)
- Per-platform targets: `dmg` for macOS, `nsis` + `portable` for Windows, `AppImage` + `deb` for Linux
- Architecture: `x64` and `arm64` for macOS, `x64` for Windows and Linux initially

### Native modules

`better-sqlite3` and `keytar` are native Node modules. electron-builder's `@electron/rebuild` (invoked automatically) rebuilds them against Electron's Node version during the build. In development, a postinstall hook runs `electron-rebuild` to match the dev Electron version.

### Code signing and notarization (macOS)

Required for users to install without "unidentified developer" warnings.

Setup:
1. Enroll in the Apple Developer Program ($99/year).
2. Create a Developer ID Application certificate.
3. Store it in the macOS keychain on the build machine.
4. Configure electron-builder's `mac.identity` to the cert name.
5. Configure `mac.hardenedRuntime: true` and add entitlements for the features Atlas uses (network, file access, JIT for the Electron runtime).
6. Configure notarization via electron-builder's `mac.notarize` with an App Store Connect API key.

The notarization flow: build → sign → upload to Apple → wait for notarization ticket → staple ticket to the `.dmg`. This takes 5–15 minutes per build and must complete before distribution.

For open source, the API key and cert live in a secure CI secret store. A GitHub Actions workflow triggered by release tags performs the signed build.

### Auto-update

`electron-updater` against GitHub Releases. On release, the GitHub Actions workflow uploads signed installers and a `latest-mac.yml` metadata file. The app checks for updates on launch (and periodically) and prompts the user to install. Auto-update respects user-configured preferences (manual vs. auto vs. off).

### Release process

1. Create a release branch `release/vX.Y.Z`.
2. Run full test suites, agent eval suites, and manual smoke tests.
3. Update `CHANGELOG.md`.
4. Bump version via changesets.
5. Tag `vX.Y.Z` on the release branch.
6. Push tag — CI builds, signs, notarizes, and publishes a draft GitHub Release.
7. Manually review the draft, then publish.
8. Merge the release branch back to main.

---

## 3. Observability and debugging

### Logs

Structured JSON logs in `{userData}/logs/atlas.log`. Daily rotation. A log viewer in Settings lets users open the logs directory or copy the most recent N lines to clipboard for bug reports (with scrubbing for secrets).

### Metrics

Atlas does not emit metrics to any external system. For local introspection:
- Cost dashboard shows financial metrics.
- A simple in-app metrics view (Settings → Debug) shows: run counts per agent, average durations, error rates, cache hit rates on `atlas-web.fetch`, active worker count.

### Debugging aids

- **Trace viewer** — the primary debugging tool for agent issues. See `docs/02-agent-runtime.md §10`.
- **Replay** — any run can be replayed in eval mode to compare before/after a prompt or code change.
- **Debug mode toggle** — in Settings, flips log level to `debug` and enables more verbose tool output in the trace.
- **DevTools** — accessible via a developer menu in debug mode for the renderer.

### Bug reports

When a user hits a bug and wants to report it, Atlas offers a "Create bug report" action that:
1. Collects the last N log lines.
2. Collects the relevant run trace(s).
3. Runs the scrubbing pipeline (redact profile, credentials, PII patterns).
4. Writes the result to a zip file the user can attach to an issue.

The scrubbing pipeline is conservative: when in doubt, redact. Users can inspect the zip before sharing.

---

## 4. Development workflow

### Setup

- Node 20+ (check with a `engines` field and a preinstall check).
- pnpm 9+.
- A `.tool-versions` file for `asdf` users.
- A `./scripts/setup.sh` that installs dependencies, rebuilds native modules, and runs initial DB migrations.

### Commands

- `pnpm dev` — run the app in dev mode
- `pnpm build` — full build
- `pnpm test` — run all tests
- `pnpm test:unit` — unit only
- `pnpm test:integration` — integration only
- `pnpm test:e2e` — e2e
- `pnpm eval` — run agent eval suites
- `pnpm lint` — ESLint + Prettier check
- `pnpm format` — Prettier write
- `pnpm typecheck` — tsc across all packages
- `pnpm db:migrate` — run pending migrations on dev DB
- `pnpm db:generate` — generate Drizzle migration from schema change

### Git conventions

- **Trunk-based development.** Work on main, feature branches for work > a day, release branches for releases.
- **Conventional Commits.** `feat:`, `fix:`, `chore:`, `refactor:`, `docs:`, `test:`. Used to generate changelogs.
- **Changesets** for versioning: every PR that changes behavior includes a changeset file describing the change.

### Refactoring discipline

The project is large and will accumulate crust. Schedule a light refactor pass at the end of every phase — not a rewrite, just a cleanup. Look for: duplicated logic, over-long files, leaky abstractions, missing tests for edge cases found during the phase, and prompts that could be shorter.

---

## 5. PDF generation pipeline

### Why Puppeteer for PDF

Puppeteer renders HTML/CSS with the full Chromium engine, including proper text shaping, font rendering, and CSS paged media. It produces PDFs indistinguishable from what you'd see in print preview. Alternatives (PDFKit, React-PDF) have worse typography and less flexible layout.

**Atlas's Puppeteer usage for PDF is distinct from its Playwright usage for scraping/submission.** A dedicated Puppeteer instance in the PDF rendering path, sharing the same Chromium binary that Playwright uses but with separate browser contexts.

### Template rendering flow

1. `atlas-fs.render_pdf(template_id, context)` is called.
2. The tool loads the template's HTML and CSS from `packages/pdf-templates/{template_id}/`.
3. The context is validated against the template's Zod schema.
4. The template is rendered (mustache substitution) to a complete HTML string.
5. A temporary HTML file is written with inlined CSS and base64-encoded font data (so the renderer has no external dependencies).
6. Puppeteer loads the HTML from a `file://` URL.
7. `page.pdf()` is called with print-appropriate options (format: Letter or A4 based on context, margins, background printing enabled).
8. The PDF is written to the output path.
9. The HTML temp file is cleaned up.

### Typography

- Fonts are bundled as woff2 files in the template directory and loaded via `@font-face` with base64-encoded data in the final HTML to ensure they're embedded in the PDF.
- Space Grotesk for headings, DM Sans for body in the default template.
- Font metrics are finalized at template design time — don't try to auto-fit content to one page at render time. The template assumes content fits; the generator is responsible for output length.

### Multiple templates

Each template is self-contained in its own directory. Adding a template is adding a directory, registering it in the template index, and optionally writing a preview image for the Settings picker. Templates share a common context schema (the canonical CV data shape) so the CV Tailor Agent's output works across all templates without modification.

For the generation subsystem that produces the context this pipeline consumes, see `docs/05-subsystems-discovery-evaluation-generation.md §4`.

---

## 6. First-run experience

When the app launches for the first time with no profile, the user sees an onboarding flow:

1. **Welcome screen.** Explains what Atlas is in two sentences. "Atlas helps you find and apply to jobs with AI agents working on your behalf. Everything runs on your machine — your data doesn't leave your computer."
2. **Import profile.** File picker for PDF, DOCX, YAML, JSON, Markdown, or "paste text." The Profile Parser Agent runs and produces canonical YAML. The user reviews and edits.
3. **Provider setup.** Add at least one LLM provider API key. The user picks a model routing preset (e.g., "Claude Sonnet for everything," "Mix: Haiku for triage, Sonnet for evaluation," "Local-only Ollama"). Each preset explains its tradeoffs.
4. **Budget setup.** Set a monthly spend cap. Defaults to $20 with prominent explanation of what that buys.
5. **Source setup.** Show the 45+ pre-configured companies with checkboxes. User picks the ones they care about. Option to add custom sources later.
6. **Story Bank intake offer.** Explains what the Story Bank is and offers the interactive intake. Can be skipped and done later.
7. **Ready.** First discovery run kicks off. User lands on the Dashboard with a "discovering…" indicator.

The whole flow takes 5–15 minutes depending on whether the user accepts the Story Bank intake. **It is the single most important UX in the app — if users bounce here, nothing else matters.** Treat it accordingly.

---

## 7. Operational runbook

A short section for "things that go wrong and what to do."

**The DB got corrupted.** Atlas keeps automatic backups under `{userData}/backups/`. Settings has a "restore from backup" option. Manual recovery: close the app, replace `atlas.sqlite` with a backup, restart.

**A run is stuck.** Use the kill switch. If the kill doesn't work (shouldn't happen but), force-quit the worker via the debug panel (Settings → Debug → Workers → Kill).

**Costs are higher than expected.** Check the Cost Dashboard for the culprit. Common causes: an agent looping on a broken tool, a model with higher rates than expected, an overly-broad search scope. Lower the budget in Settings to force a hard stop.

**A scraper adapter is failing.** Check the Source Health dashboard. If a known platform broke, disable the source and fall back to the generic agent path. File a bug with saved HTML for the maintainer.

**An application submitted when it shouldn't have.** This should never happen in HITL mode. If it does: (a) check the trace for the approval event — there should be one; if not, it's a gating bug to report urgently. (b) Contact the recruiter to withdraw. Atlas tracks the application and can prefill a withdrawal email.

**The LLM is returning garbage.** Check the model routing in Settings. Try a different model for the affected stage. Inspect the trace to see what the model actually received.

**Playwright MCP won't start.** Usually a native dependency issue. Run the setup script to rebuild native modules. If persistent, check the logs for the specific error.
