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
