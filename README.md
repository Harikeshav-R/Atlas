# Atlas

**A local-first, terminal-native job-application co-pilot for software engineers.**

Atlas discovers matching jobs, tailors a one-page resume and cover letter per posting from
a single master resume, drafts application-form answers, and tracks every application
through to offer — all driven by AI that runs either through a coding CLI already installed
on your machine (Claude Code, OpenAI Codex, Google Antigravity) or through a hosted API
(OpenRouter, Amazon Bedrock, Anthropic, …).

> **Status:** Early implementation (Phase 0 foundations). The full design is in
> [`docs/PROJECT.md`](./docs/PROJECT.md); current progress is tracked in
> [`docs/STATUS.md`](./docs/STATUS.md).

The first commands are live. Check your AI backend setup with:

```bash
atlas doctor          # report each configured backend's availability
atlas doctor --probe  # also run a live capability round-trip (makes a billable call)
atlas doctor --json   # machine-readable, for scripting
atlas -v doctor       # -v/-vv (or --log-level DEBUG) raises log verbosity
```

Onboard and manage your search profiles:

```bash
atlas init                 # first-run Q&A: your details + first search profile
atlas profile list         # list profiles (● marks the active one)
atlas profile list --json  # machine-readable, for scripting
atlas profile add          # create another profile (becomes active)
atlas profile edit <id>    # edit a profile (current values offered as defaults)
atlas profile use <id>     # make a profile the active one
```

Ingest and version your single master resume (a Markdown file):

```bash
atlas resume set <path>    # ingest/point at your resume (new version only if it changed)
atlas resume reparse       # re-parse the current resume into a new version
atlas resume show          # list stored versions (● marks the latest)
atlas resume show --json   # machine-readable, for scripting
atlas resume render        # render the latest version to a one-page PDF (Jake's-résumé theme)
atlas resume render --json # machine-readable, for scripting
```

`atlas resume render` produces the PDF via an HTML/CSS → PDF pipeline (WeasyPrint
by default) and reports the output path and measured page count; if the resume
overflows one page it warns you (tailoring, coming next, trims it to fit).

Scrape a job posting from a URL, inspect what was saved, and score it for fit:

```bash
atlas add <url>            # scrape + parse a posting, save it, and score it for fit
atlas postings list        # list saved postings (with their latest fit score)
atlas postings show <id>   # show one posting's normalized fields + latest fit
atlas postings list --json # machine-readable, for scripting

atlas score <id>           # (re)score a saved posting for fit against the active profile
atlas score <id> --json    # machine-readable, for scripting

atlas tailor <id>          # tailor your resume to a saved posting → one-page PDF
atlas tailor <id> --json   # machine-readable, for scripting

atlas cover <id>           # write a cover letter for a saved posting → PDF
atlas cover <id> --tone warm  # pick the tone

atlas render <app_id>      # re-render an application's resume + cover PDFs (no AI)
atlas open <app_id>        # open an application's exported PDFs in the default viewer
```

Track each application through its pipeline:

```bash
atlas status set <app_id> <stage>       # move to a stage (saved…offer/rejected/…)
atlas status set <app_id> oa --due 2026-08-15   # record an advisory deadline
atlas status set <app_id> <stage> --force       # override the state machine
atlas apply mark <app_id>               # mark applied (records the applied date)
atlas list                              # list tracked applications, newest first
atlas list --status applied --profile 1 # filter by stage and/or profile
atlas list --json                       # machine-readable, for scripting
```

Or browse and track it all interactively:

```bash
atlas tui                               # launch the interactive TUI
```

`atlas add` scores a newly-saved posting automatically; if you haven't set an
active profile or a master resume yet, it saves the posting and points you at
`atlas score`. Scoring combines an AI fit assessment (score, verdict, rationale,
matched strengths, gaps) with deterministic salary / location / work-auth /
deal-breaker signals shown as badges. Re-scoring appends a new assessment rather
than replacing the last one.

`atlas tailor` builds a truth-anchored, one-page tailored resume for a posting:
an AI pass selects and rewords the most relevant master-resume content (governed
by the `[tailoring] honesty_level`), a safety net restores any dropped dates, and
a render-measure-trim loop packs it onto one page. It reports the PDF path and any
posting keywords it couldn't truthfully support; re-tailoring keeps a new version.

`atlas cover` writes a cover letter grounded in your tailored resume (or master
resume) and the posting, rendered to a PDF matching the résumé styling. Tailoring
and the cover letter are collected under an **application** for the posting;
`atlas render <app_id>` regenerates its PDFs from stored content (no AI), and
`atlas open <app_id>` opens them in your default viewer.

`atlas status set` / `atlas apply mark` move an application through its pipeline
(`saved → preparing → ready → applied → oa → interview → offer / rejected /
withdrawn / ghosted`). Each move is validated against the state machine — an
illegal jump is refused with a hint (pass `--force` to override) — and recorded
in a timestamped status history; reaching `applied` stamps the applied date and a
terminal stage records the outcome. `atlas list` shows your tracked applications,
newest-updated first, filterable by `--status` and `--profile`.

`atlas tui` launches the interactive Textual app: a Dashboard (pipeline funnel,
active profile, recent activity, upcoming deadlines), a **Discover** queue (press
`w`) that ranks your scored postings by fit and lets you tailor / dismiss / save /
open a posting's apply URL and drill into its detail, an Applications view (table
or Kanban board, with in-app status changes), drill-through to Application and
Posting detail, and a **Tailor workspace** (press `t` on an application) that shows
your master resume and tailored selections and runs Tailor / Cover letter /
Re-render / Open — each off the UI thread so long AI and rendering calls never
freeze the app. When no AI backend is configured the TUI still opens for browsing
and those actions are disabled (run `atlas doctor` to set the backend up).
Inline editing of selections and per-section regenerate are coming next.

Discover jobs from company ATS boards:

```bash
atlas company add <url>     # watchlist a company's ATS board (auto-detects the ATS)
atlas company add <url> --name "Acme Inc"   # override the display name
atlas company list          # list watchlisted boards (--json for scripting)
atlas discover              # poll the watchlist now for new postings (--json)
```

`atlas company add` auto-detects the ATS provider and board token from a
careers/board URL — **Greenhouse** (`boards.greenhouse.io/<token>`), **Lever**
(`jobs.lever.co/<site>`), **Ashby** (`jobs.ashbyhq.com/<name>`), and **Workday**
(`<tenant>.<wdN>.myworkdayjobs.com/<site>`) are supported, and each provider's raw
API URL is accepted too — then adds the company to your watchlist; an unrecognized
URL is refused with the list of supported providers. `atlas discover` runs one poll
now, fetching each enabled board, normalizing and de-duplicating its postings
(against both what discovery and `atlas add` already saved), and saving the new
ones; it's AI-free and points you at `atlas score` (or the daemon) to score them.

Run background work with the daemon:

```bash
atlas daemon start          # run the scheduler in the foreground (blocking)
atlas daemon status         # report running/stopped (--json for scripting)
atlas daemon stop           # stop a running daemon
```

`atlas daemon start` runs a scheduler that, on the `[discovery]`
`poll_interval_minutes` interval, first **discovers** new postings from your ATS
watchlist and then **scores** any not-yet-scored postings against your active
profile — so newly-found roles are scored on the same pass. (Aggregator sources
and the daemon's IPC link to the TUI arrive next.) It blocks the terminal;
background it with your OS service manager (`systemd --user`, `launchd`, Task
Scheduler).

Logs go to stderr (so stdout / `--json` stays clean) and to a rotating file
under your platform's state directory; verbosity follows `--log-level` / `-v` /
the `ATLAS_LOG_LEVEL` env var / the `[logging]` config.

## Highlights

- **Bring-your-own-AI** — pluggable backends; coding CLIs by default, hosted APIs optional.
- **Local-first & private** — all data on your machine (SQLite + OS keychain for secrets).
- **Truth-anchored tailoring** — one-page resumes built from your master resume, with a
  traceability check on every claim.
- **Prepare, don't auto-submit** — Atlas builds the materials; you apply and it tracks the
  pipeline, calendar deadlines, and (optionally) inbox status updates.
- **Cross-platform** — Windows, macOS, and Linux.

## Documentation

Everything lives under [`docs/`](./docs/) — see [`docs/README.md`](./docs/README.md) for the
index.

- [Design document](./docs/PROJECT.md) — architecture, features, data model, roadmap.
- [Coding CLI reference](./docs/cli-reference/) — headless-mode docs for the AI backends.
- [AGENTS.md](./AGENTS.md) — working agreement for anyone (agent or human) changing the
  code: branching, commits, tests, and PR flow.

## Tech stack (planned)

Python 3.11+ · [uv](https://docs.astral.sh/uv/) · Textual + Typer · SQLModel + SQLite ·
`desktop-notifier` · Playwright + WeasyPrint. Install (once built) with
`uv tool install atlas` or `pipx install atlas`.

## License

See [LICENSE](./LICENSE).
