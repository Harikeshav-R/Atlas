# Workflow

Day-to-day git/PR flow. This is a **pointer + quick reference**; the normative rules are in
[`AGENTS.md`](../../AGENTS.md) — read it in full once, then use this as the cheat sheet.

## The loop

1. **Branch** off fresh `main` — never work on `main`:
   ```bash
   git switch main && git pull --ff-only
   git switch -c <type>/<short-kebab-description>
   ```
   `<type>` ∈ `feat|fix|docs|refactor|test|perf|build|ci|chore`. (AGENTS.md §2)
2. **Commit** in Conventional Commits, **one logical change each**, green at every commit,
   **no AI attribution** (no `Co-Authored-By` AI, no "Generated with", no model names/emojis
   in messages). Code + its tests go in the same commit. (AGENTS.md §3–§4)
3. **Gates green before committing:** `ruff format --check`, `ruff check`, `mypy --strict`,
   `pytest` at 100% coverage. `pre-commit` enforces the fast subset; don't bypass it.
4. **Stay current:** rebase on `main`; you may tidy your own history **before** review; **no
   force-push once review has started**. (AGENTS.md §9)
5. **Open a PR** (`gh pr create`) → **stop for human review**. Do **not** self-merge.
   (AGENTS.md §7) Merge strategy is **merge commit**, so per-commit hygiene matters.

## Definition of Done (summary — full list in AGENTS.md §8)

- Correct branch; conventional, one-change, green commits; no AI attribution.
- ruff + `mypy --strict` clean; tests extensive; **100% line + branch** (pragmas justified).
- Docstrings + type hints on public API.
- Docs updated: [PROJECT.md](../PROJECT.md) (if architecture/data-model/scope changed),
  `CHANGELOG.md` (Unreleased entry), README/usage (if user-facing behavior changed), and the
  relevant [`docs/agent/`](./README.md) doc if a convention changed.
- DB change → Alembic migration in the same PR. Dep change → `pyproject.toml` + `uv.lock`
  together in a `build` commit.
- PR opened for human review; not self-merged.

## When unsure

Ask before implementing, or surface the ambiguity in the PR (AGENTS.md §11). Better to ask
than to confidently build the wrong thing.

## Environment note

`origin` may be configured for SSH with a key that lacks write access in some setups; pushes
can be done over the `gh`-authenticated HTTPS remote if SSH is rejected. This is an
environment detail, not a project rule.
