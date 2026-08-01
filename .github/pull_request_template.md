<!--
Thanks for contributing to Atlas! Please read AGENTS.md before opening a PR.
Do NOT include any AI/assistant authorship attribution in the title or body
(AGENTS.md §4).
-->

## What & why

<!-- What does this change do, and why? Link the design section it implements
     (docs/PROJECT.md) where relevant. -->

## Key commits

<!-- List the notable commits (each is one logical, Conventional Commit change). -->

## Breaking changes / migrations

<!-- Note any BREAKING CHANGE and any Alembic migration included in this PR.
     Write "None" if not applicable. -->

None.

## How tested

<!-- How did you verify this? Confirm the quality gates are green locally. -->

## Related issues

<!-- e.g. Closes #123 / Refs #123 -->

---

## Definition of Done (AGENTS.md §8)

- [ ] Work is on a correctly named branch off latest `main` (never on `main`).
- [ ] Commits are Conventional, one-logical-change, green at each step, with **no AI attribution**.
- [ ] `uv run ruff format --check .`, `uv run ruff check .`, and `uv run mypy --strict .` pass with zero errors.
- [ ] Tests are extensive and the suite passes at **100% line + branch coverage** (any pragmas justified).
- [ ] Public modules/classes/functions have **docstrings and full type hints**.
- [ ] [`docs/PROJECT.md`](../docs/PROJECT.md) updated when the change affects architecture, the data model, features, or scope.
- [ ] `CHANGELOG.md` updated under `Unreleased` ([Keep a Changelog](https://keepachangelog.com/)).
- [ ] README / usage docs updated when user-facing CLI/TUI behavior changes.
- [ ] DB/schema changes include an Alembic migration in the same PR.
- [ ] Dependency changes update both `pyproject.toml` and `uv.lock` in one `build` commit.
- [ ] PR opened for human review; not self-merged.
