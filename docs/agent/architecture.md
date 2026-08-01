# Architecture (for agents)

A working map of the system so you know where code goes. Authoritative detail:
[PROJECT.md §4](../PROJECT.md#4-high-level-architecture),
[§5 (components)](../PROJECT.md#5-component-specifications),
[§14 (layout)](../PROJECT.md#14-proposed-project-layout).

## Process model

- **`atlas daemon`** — long-running background process. Owns the scheduler (APScheduler):
  discovery polling, AI scoring, optional email scan; fires desktop notifications; writes to
  SQLite. Exposes local IPC (Unix socket / named pipe) for the TUI to trigger work.
- **TUI client (`atlas` / `atlas tui`)** — the interactive Textual app. Reads/writes the same
  SQLite DB; talks to the daemon over IPC for on-demand work; runs standalone if the daemon
  is down (only scheduled background discovery needs the daemon).
- **CLI subcommands** — thin scriptable entry points (`atlas add`, `atlas tailor`, …).

**Concurrency:** SQLite in WAL mode. Daemon is the single writer for discovery/scoring rows;
TUI writes user-driven rows. Short transactions. Assume one daemon writer.

## Module map (`src/atlas/`)

| Package | Responsibility |
|---|---|
| `config/` | TOML config + secrets via keyring; `platformdirs` paths |
| `db/` | SQLModel models, session, Alembic migrations |
| `ai/` | `LLMProvider` interface, `cli/` subprocess adapters, `api/` LiteLLM provider, `prompts/` (Jinja2), `complete_json.py`, cache + router |
| `profiles/` | onboarding Q&A, preferences (multiple profiles) |
| `resume/` | master resume parse + versioning |
| `discovery/` | `ats/` + `aggregators/` adapters + poller |
| `scrape/` | fetch + extract → normalized `JobPosting` |
| `matching/` | fit scoring |
| `tailor/` | selection, diff-mode tailoring, one-page packing, safety nets |
| `coverletter/`, `questions/` | letter + form-answer drafting (+ answer library) |
| `render/` | HTML/CSS → PDF (WeasyPrint default / Chromium option), themes |
| `tracking/` | applications, status state machine, analytics |
| `calendar/`, `email/` | CalDAV + `.ics`; IMAP read-only scan |
| `daemon/` | scheduler + IPC server |
| `tui/` | Textual app, screens, widgets |
| `notify/` | `desktop-notifier` wrapper |

## Design rules that keep the shape clean

- **Adapters behind interfaces.** Job sources, AI backends, calendar/email, notifier — all
  behind an interface so they're swappable and fakeable in tests.
- **No I/O in pure logic.** Keep matching/tailoring/packing logic free of network/DB/file
  calls; inject the boundaries (clock, subprocess runner, HTTP client, DB session).
- **Files vs DB.** SQLite stores structured data + references; resumes/PDFs/HTML snapshots
  live on disk under the data dir. Don't put blobs in the DB.
- **Schema changes ship with an Alembic migration** in the same PR.

## New code checklist

- Put it in the right package above; if it's a new external integration, add an interface.
- Add/extend SQLModel models + a migration if persistence changes.
- Update [PROJECT.md](../PROJECT.md) if you changed architecture, the data model, or scope.
