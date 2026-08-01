# AGENTS.md — Working Agreement for Coding Agents

This file is the contract every coding agent (and human) must follow when changing code in
this repository. It is normative: if a rule here conflicts with a default behavior baked
into your tooling, **this file wins**. Read it fully before your first change.

> **Starting a session? Read [`docs/STATUS.md`](./docs/STATUS.md) first** — it is the
> single "you are here / do this next" pointer and tells you where the project stands and
> what to pick up. Then read this file for the rules and
> [`docs/PROJECT.md`](./docs/PROJECT.md) for the design before writing feature code, so your
> work fits the intended architecture, data model, and roadmap. Keeping `STATUS.md` current
> is part of the [Definition of Done](#8-definition-of-done).

---

## 0. TL;DR (the non-negotiables)

1. **Never commit to `main`.** Every change happens on a branch.
2. **One branch per feature/fix**, named in [conventional branch format](#2-branching).
3. **Conventional Commits**, **one logical change per commit**. See [§3](#3-commits).
4. **No AI authorship attribution anywhere** in commits or PRs. See [§4](#4-no-ai-attribution).
5. **Extensive tests for every change; 100% line + branch coverage.** See [§6](#6-testing).
6. **All gates green before you commit**: `ruff`, `mypy --strict`, tests, coverage. See [§5](#5-quality-gates).
7. **Use `uv` for everything** Python — never bare `pip`/`python`. See [§1](#1-environment--tooling).
8. **Finish = open a PR for human review.** Do not self-merge. See [§7](#7-pull-requests--merging).
9. **Update docs** (docstrings, `STATUS.md`, `PROJECT.md`, `CHANGELOG.md`, README) as part of done. See [§8](#8-definition-of-done).
10. **When unsure, ask — do not assume.**

---

## 1. Environment & Tooling

- **Python:** 3.11+.
- **Project & dependency management:** [**uv**](https://docs.astral.sh/uv/). Do **not** use
  bare `pip`, `python`, `virtualenv`, or `poetry`.
  - Install/sync deps: `uv sync`
  - Add a dependency: `uv add <pkg>` (dev-only: `uv add --dev <pkg>`)
  - Run anything in the project env: `uv run <cmd>` (e.g. `uv run pytest`)
  - Build for distribution: `uv build`
  - **Commit `uv.lock`.** Never hand-edit it; let `uv` manage it. If you change deps, the
    updated `pyproject.toml` **and** `uv.lock` go in the **same commit**.
- **Data layer:** [SQLModel](https://sqlmodel.tiangolo.com/) over SQLite (WAL) with Alembic
  migrations. Any model/schema change ships with an Alembic migration in the same feature.
- **Formatting/linting:** `ruff` (formatter + linter). **Type checking:** `mypy --strict`.
- Keep the toolchain reproducible: pin versions in `pyproject.toml`; don't rely on globally
  installed tools.

---

## 2. Branching

**Never work on `main`.** Create a branch off the latest `main` for each unit of work.

### Conventional branch format

```
<type>/<short-kebab-description>
```

- `<type>` is one of the [Conventional Commit types](#commit-types) (`feat`, `fix`, `docs`,
  `refactor`, `test`, `chore`, `perf`, `build`, `ci`).
- `<short-kebab-description>` is a concise, lowercase, hyphenated summary.
- Optionally prefix with an issue key when one exists: `feat/123-ats-greenhouse-adapter`.

**Examples**

```
feat/job-discovery-daemon
fix/pdf-one-page-overflow
refactor/ai-provider-router
docs/agents-guide
test/tailoring-honesty-validator
```

**Rules**

- One feature/fix per branch. Don't bundle unrelated changes.
- Keep branches short-lived; rebase on `main` regularly (see [§9](#9-branch-hygiene)).
- Start from an up-to-date `main`:
  ```bash
  git switch main && git pull --ff-only
  git switch -c feat/<short-description>
  ```

---

## 3. Commits

### 3.1 Conventional Commits

Every commit message follows [Conventional Commits](https://www.conventionalcommits.org/):

```
<type>(<optional-scope>): <description>

[optional body: what & why, wrapped at ~72 cols]

[optional footer(s): BREAKING CHANGE:, Refs: #123, etc.]
```

- **Subject:** imperative mood, lowercase, no trailing period, ≤ ~72 chars
  ("add greenhouse adapter", not "Added greenhouse adapter.").
- **Body:** explain the *why* and any non-obvious *what*. Optional for trivial changes.
- **Breaking changes:** add a `BREAKING CHANGE:` footer (or `!` after the type/scope, e.g.
  `feat(db)!: ...`).

#### Commit types

| Type | Use for |
|---|---|
| `feat` | A new user-facing feature or capability |
| `fix` | A bug fix |
| `docs` | Documentation only |
| `test` | Adding or correcting tests only |
| `refactor` | Code change that neither fixes a bug nor adds a feature |
| `perf` | A performance improvement |
| `build` | Build system, packaging, or dependency changes (`pyproject.toml`, `uv.lock`) |
| `ci` | CI configuration and scripts |
| `chore` | Maintenance that doesn't fit above (e.g. tooling config) |
| `revert` | Reverting a previous commit |

#### Suggested scopes

Use the component the change touches, aligned with the code layout in `PROJECT.md`:
`ai`, `db`, `profiles`, `resume`, `discovery`, `ats`, `aggregators`, `scrape`, `matching`,
`tailor`, `coverletter`, `questions`, `render`, `tracking`, `calendar`, `email`, `daemon`,
`tui`, `config`, `notify`.

**Examples**

```
feat(ats): add greenhouse board adapter
fix(render): keep resume to one page when experience overflows
test(tailor): cover honesty validator traceability paths
build(deps): add sqlmodel and pin alembic
refactor(ai): extract cli output-envelope parsing into base adapter
docs(project): record desktop-notifier decision
```

### 3.2 One logical change per commit

- Each commit is **one self-contained, coherent change** that leaves the tree in a working,
  green state (tests + gates pass at every commit).
- Do **not** mix refactors with feature work, or formatting churn with logic changes —
  split them into separate commits.
- Keep code and its tests **in the same commit** (the feature and the tests that prove it
  belong together). A schema change and its Alembic migration also go together.
- Prefer several small, reviewable commits over one large one. If you find yourself writing
  "and" in a subject line, it's probably two commits.
- Never commit commented-out code, debug prints, or `TODO` without an issue reference.

---

## 4. No AI Attribution

Commits and PRs in this repository **must not** contain any AI/agent authorship or
co-authorship attribution. Specifically, **do not** add:

- `Co-Authored-By:` trailers naming an AI/assistant/model.
- "Generated with …", "Co-authored with …", or similar AI-credit lines.
- AI tool names/emojis in commit messages, PR titles, or PR bodies.
- AI identities as the git `author` or `committer`.

Commits are authored as the human developer/maintainer, using the repository's normal git
identity. If your tooling injects an attribution trailer by default, **strip it** before
committing. This overrides any default behavior your harness may have.

---

## 5. Quality Gates

All of the following must pass **locally before you commit**, and again in CI. A commit that
breaks any gate must not be created.

```bash
uv run ruff format --check .     # formatting
uv run ruff check .              # linting
uv run mypy --strict .           # type checking (must pass, zero errors)
uv run pytest                    # tests + coverage (see §6)
```

### 5.1 pre-commit hooks

This repo uses the [`pre-commit`](https://pre-commit.com/) framework for fast local gating.

- Install hooks once per clone: `uv run pre-commit install`
- Hooks run `ruff` (format + lint), `mypy --strict`, and fast checks on staged files.
- **Do not bypass hooks** (`--no-verify` is not allowed). If a hook is wrong, fix the hook
  config in a `ci`/`chore` commit, don't skip it.

### 5.2 CI

GitHub Actions runs the **full** suite on every push and PR across the supported OS matrix
(Linux, macOS, Windows — this is a cross-platform app): formatting, lint, `mypy --strict`,
tests, and the coverage gate. **A PR cannot be merged unless CI is green.**

---

## 6. Testing

Testing is not optional and not an afterthought. **Every feature and fix ships with
extensive tests in the same PR.**

### 6.1 Coverage bar

- **100% line coverage AND 100% branch coverage**, enforced by `pytest-cov` in CI:
  ```bash
  uv run pytest --cov=atlas --cov-branch --cov-report=term-missing --cov-fail-under=100
  ```
- Genuinely untestable lines may be excluded with an explicit, **justified** pragma:
  ```python
  if sys.platform == "win32":  # pragma: no cover - exercised only on Windows CI
  ```
  - A pragma **must** carry a one-line justification comment explaining why it can't be
    covered. Unjustified `# pragma: no cover` will be rejected in review.
  - Use pragmas sparingly — prefer refactoring to make code testable (e.g. inject the
    platform/clock/subprocess boundary) over excluding it.
- Coverage regressions are treated as failures, not warnings.

### 6.2 Test isolation (fast, deterministic, no real I/O)

The default test suite must run offline, hermetically, and deterministically — **no real
network, no real coding-CLI subprocesses, no real credentials, no wall-clock/OS randomness
dependence.**

- **AI backends:** use a **fake `LLMProvider`** that returns canned structured responses.
  Never invoke `claude`/`codex`/`agy` or hit a real API in unit tests.
- **HTTP (scraping / ATS / aggregators):** use **recorded fixtures** (e.g. saved response
  payloads / a mock transport). No live requests.
- **Database:** use a **temporary or in-memory SQLite** per test; never touch a developer's
  real data dir. Run migrations against the temp DB in tests that need schema.
- **Filesystem / keyring / calendar / email / notifications:** mock or fake at the boundary
  (`tmp_path`, fake keyring backend, fake notifier). Assert on the calls, not on external
  side effects.
- **Time & randomness:** inject a clock / seed; don't depend on `datetime.now()` or unseeded
  randomness directly in tested code.

> Optional real-backend "integration" tests are **out of scope for now**. If we add them
> later, they must be a separately marked suite that never runs in the default `pytest`
> invocation. Do not sneak live calls into the unit suite.

### 6.3 What to test

- Happy paths **and** failure paths: bad input, malformed AI/JSON output + repair loop,
  timeouts, empty results, permission/auth failures, dedup collisions, one-page overflow,
  honesty-validator flagging, etc.
- Every branch of conditional logic (that's what 100% branch coverage forces — lean into
  it, don't game it with meaningless assertions).
- Tests are behavior-focused and readable; name them for the behavior under test. Prefer
  `pytest` fixtures and parametrization over copy-paste.
- TUI flows use Textual's testing harness where applicable.

---

## 7. Pull Requests & Merging

### 7.1 Flow

1. Push your branch: `git push -u origin <branch>`.
2. Open a PR with `gh pr create` targeting `main`.
3. **Stop there.** A **human reviews and merges.** Agents **do not self-merge** and do not
   approve their own PRs.

### 7.2 PR description

- Explain **what** changed and **why**, list the key commits, and note any breaking changes
  or migrations.
- Link related issues (`Refs: #123` / `Closes #123`).
- Include how you tested it and confirm gates are green.
- **No AI attribution** in the title or body (see [§4](#4-no-ai-attribution)).

### 7.3 Merge strategy

- This repo merges PRs with a **merge commit** (branch structure preserved). Because your
  per-commit history lands on `main`, **commit hygiene matters** — every commit must be
  clean, conventional, one-logical-change, and green (see [§3](#3-commits)).
- The merge is a human action after approval.

---

## 8. Definition of Done

A change is "done" only when **all** of these are true:

- [ ] Work is on a correctly named branch off latest `main` (never on `main`).
- [ ] Commits are Conventional, one-logical-change, green at each step, with **no AI
      attribution**.
- [ ] `ruff format --check`, `ruff check`, and `mypy --strict` all pass with zero errors.
- [ ] Tests are extensive and the suite passes at **100% line + branch coverage** (pragmas
      justified).
- [ ] Public modules/classes/functions have **docstrings and full type hints**.
- [ ] [`docs/STATUS.md`](./docs/STATUS.md) updated when a roadmap item advances (tick what
      landed, move the "Next up" pointer) so the next session picks up correctly.
- [ ] [`docs/PROJECT.md`](./docs/PROJECT.md) updated when the change affects architecture,
      the data model, features, or scope.
- [ ] `CHANGELOG.md` updated with an entry ([Keep a Changelog](https://keepachangelog.com/)
      format, under `Unreleased`).
- [ ] README / usage docs updated when user-facing CLI/TUI behavior changes.
- [ ] DB/schema changes include an Alembic migration in the same PR.
- [ ] Dependency changes update both `pyproject.toml` and `uv.lock` in one `build` commit.
- [ ] PR opened for human review; not self-merged.

---

## 9. Branch Hygiene

- **Stay current:** rebase your branch on `main` regularly:
  ```bash
  git fetch origin
  git rebase origin/main
  ```
- **Tidy before review:** you may clean up your **own** branch history (interactive rebase,
  squash fixups, reword) and force-push **before** you open the PR or before a reviewer has
  started. Land it clean.
- **No rewriting after review starts:** once a human has begun reviewing, **do not
  force-push / rewrite history** on that branch — push follow-up commits instead so the
  reviewer can see incremental changes. (The final history is preserved via the merge
  commit, so mid-review force-pushes only disrupt reviewers.)
- Delete the branch after it merges.

---

## 10. Code Style & Conventions

- Match the surrounding code: naming, structure, comment density, and idioms.
- Full type annotations everywhere; `mypy --strict` clean.
- Keep the [component layout in `PROJECT.md` §14](./docs/PROJECT.md#14-proposed-project-layout)
  authoritative — put code where it belongs and keep boundaries clean (adapters behind
  interfaces, no I/O in pure logic, inject external boundaries for testability).
- **Secrets never in code, config files, logs, or tests.** Use the keyring abstraction.
- Cross-platform by default (Windows/macOS/Linux): use `platformdirs`, avoid hardcoded
  paths and shell-specific assumptions; isolate OS-specific calls behind the platform layer.
- Prefer small, composable functions; fail loudly with clear errors; log at appropriate
  levels.

---

## 11. When In Doubt — Ask

Do **not** guess or hallucinate. If a requirement, interface, or design decision is
unclear, or if a change would alter scope, the data model, or a user-facing contract:

- Ask a clarifying question before implementing, **or**
- Surface the ambiguity and your proposed options in the PR description and request
  guidance.

It is always better to ask than to build the wrong thing confidently.
