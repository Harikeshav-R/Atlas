# Atlas — Project Status (start here)

> **New session? Read this file first, then [`AGENTS.md`](../AGENTS.md).** This is the
> single "you are here / do this next" pointer. It tells a fresh coding-agent (or human)
> session where the project stands and what to pick up, without reverse-engineering it
> from git history.
>
> **Keep it current.** Updating this file is part of the [Definition of Done](../AGENTS.md#8-definition-of-done):
> whenever a roadmap item lands, tick it here and move the "Next up" pointer. A stale
> STATUS.md is a bug.

- **Last updated:** 2026-08-01
- **Current phase:** Phase 0 — Foundations (in progress)
- **Design source of truth:** [`docs/PROJECT.md`](./PROJECT.md) — especially the
  [phased roadmap](./PROJECT.md#15-phased-roadmap).
- **Working agreement:** [`AGENTS.md`](../AGENTS.md) (branching, commits, tests, PR flow).

---

## ▶ Next up (do this next)

**Phase 0 · AI provider abstraction — CLI adapters.** The core contract has landed
(step 1 + the shared `complete_json()` recovery ladder — see "What has landed"). Continue
`atlas.ai` per [PROJECT.md §5.1](./PROJECT.md#51-ai-provider-abstraction-atlasai) and
[Appendix A](./PROJECT.md#appendix-a--coding-cli-adapter-reference):

1. ✅ `LLMProvider` protocol + `LLMRequest`/`LLMResponse`/`Usage` models (`src/atlas/ai/base.py`)
   and the `complete_json()` structured-output ladder (`src/atlas/ai/complete_json.py`).
2. **`CliAdapter` base class** (argv build, subprocess w/ timeout + process-tree kill,
   separate stdout/stderr capture, envelope parse, usage/cost mapping, error normalize).
3. **Claude Code** adapter (default CLI backend) — `--output-format json --json-schema`,
   structured-output path, isolated scratch cwd, no `--allowedTools`.
4. **OpenRouter** adapter (default API failover backend).
5. Capability probing, failover chain, and `atlas doctor`.
6. Tests: fake provider + recorded fixtures, no live CLI/API calls (AGENTS.md §6.2).

> Also still open in Phase 0 (can be done before or alongside the above, as separate PRs):
> **config + keyring**, **SQLModel + SQLite (WAL) + Alembic**, and **logging** — see the
> Phase 0 checklist in [PROJECT.md §15](./PROJECT.md#15-phased-roadmap). The OpenRouter
> adapter (step 4) depends on config + keyring landing first.

---

## ✅ What has landed

Phase 0 · AI provider abstraction — core contract:

- `atlas.ai` package with the `LLMProvider` protocol and `LLMRequest` / `LLMResponse` /
  `Usage` models, plus the `LLMError` / `LLMOutputError` hierarchy (`src/atlas/ai/base.py`).
- `complete_json()` structured-output recovery ladder (`src/atlas/ai/complete_json.py`):
  native structured field → balanced-JSON extraction → bounded content retries with
  temperature escalation → prompt-only fallback → `LLMOutputError`; generic over the
  target Pydantic model, so no `jsonschema` dependency. Reusable offline `FakeLLMProvider`
  test double in `tests/conftest.py`. First runtime dependency: `pydantic`. 100% coverage.

Phase 0 · Repository hygiene & scaffold (foundation every later PR depends on):

- uv project scaffold: `pyproject.toml` (hatchling), committed `uv.lock`, `src/atlas`
  package (`__version__`, `py.typed`), smoke tests — 100% coverage.
- Quality-gate config: `ruff` (format + lint), `mypy --strict`, `pytest` + 100%
  line/branch coverage.
- CI: `.github/workflows/ci.yml` on the Windows/macOS/Linux × Python 3.11–3.13 matrix
  via uv. `main` branch protection requires these checks green.
- `.pre-commit-config.yaml` mirroring the CI gates.
- Repo metadata: PR template (Definition of Done), issue templates, Dependabot,
  CODEOWNERS.
- `CHANGELOG.md` and `CONTRIBUTING.md`.

_(Merged via PR #4. See `git log` and closed PRs for detail.)_

---

## 🧭 How to orient a fresh session

Run these to see live state (this file is the summary; git/gh are the ground truth):

```bash
git log --oneline -15               # recent history
gh pr list --state open             # in-flight work (may need the branch)
gh pr list --state merged --limit 5 # what landed recently
git branch -a                       # existing branches
uv sync                             # install deps into the project venv
uv run pytest                       # confirm the suite is green before changing anything
```

Then: read **this file** → the **[roadmap](./PROJECT.md#15-phased-roadmap)** → the
**PROJECT.md section** for the "Next up" item → **[`AGENTS.md`](../AGENTS.md)** for the
rules, and start on a new branch.

---

## Phase progress at a glance

Detailed checklists live in [PROJECT.md §15](./PROJECT.md#15-phased-roadmap); this is the
high-level state.

| Phase | Title | State |
|---|---|---|
| 0 | Foundations (hygiene/CI · scaffold · config/DB/logging · AI providers) | 🚧 in progress — hygiene/CI + scaffold + AI provider core contract done; config/DB/logging + AI CLI/API adapters remain |
| 1 | Core loop (onboarding · resume · scrape · scoring · tailoring · tracking · TUI) | ⬜ not started |
| 2 | Discovery & background (daemon · ATS · aggregators · Discover queue) | ⬜ not started |
| 3 | Scheduling & status intelligence (CalDAV · email scan · Q&A drafting) | ⬜ not started |
| 4 | Polish & depth (analytics · more adapters · scraping · DOCX · encryption) | ⬜ not started |
