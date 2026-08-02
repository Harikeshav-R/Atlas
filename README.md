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

The first command is live — check your AI backend setup with:

```bash
atlas doctor          # report each configured backend's availability
atlas doctor --json   # machine-readable, for scripting
```

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
