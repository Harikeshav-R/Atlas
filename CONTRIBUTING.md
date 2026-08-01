# Contributing to Atlas

Thanks for your interest in improving Atlas! This project follows a strict working
agreement so that its history stays clean and every change is safe to merge.

> **Read [`AGENTS.md`](./AGENTS.md) first.** It is the normative contract for every
> change — branching, Conventional Commits, testing, quality gates, and the PR flow.
> This file is a short on-ramp; `AGENTS.md` is the source of truth and wins on any
> conflict.

## Before you start

- Read the design in [`docs/PROJECT.md`](./docs/PROJECT.md) so your work fits the
  intended architecture, data model, and roadmap.
- Check the [phased roadmap](./docs/PROJECT.md#15-phased-roadmap) and
  [non-goals](./docs/PROJECT.md#22-non-goals-explicitly-out-of-scope) to make sure
  the change is in scope.

## Environment setup

Atlas uses [**uv**](https://docs.astral.sh/uv/) for everything Python — never bare
`pip`/`python`.

```bash
uv sync                     # install dependencies into the project venv
uv run pre-commit install   # install the local pre-commit hooks (once per clone)
```

## The short version of the workflow

1. **Branch off the latest `main`** — never commit to `main`.
   ```bash
   git switch main && git pull --ff-only
   git switch -c <type>/<short-kebab-description>
   ```
2. **Make one logical change per commit**, using
   [Conventional Commits](https://www.conventionalcommits.org/). Keep code and its
   tests in the same commit.
3. **No AI authorship attribution** anywhere in commits or PRs (`AGENTS.md` §4).
4. **Run the gates locally before every commit** (they also run in CI):
   ```bash
   uv run ruff format --check .
   uv run ruff check .
   uv run mypy --strict .
   uv run pytest        # tests + 100% line/branch coverage gate
   ```
   Do not bypass pre-commit hooks (`--no-verify` is not allowed).
5. **Write extensive tests.** The suite must stay at **100% line and branch
   coverage**; any `# pragma: no cover` needs a one-line justification.
6. **Update docs** as part of "done": docstrings, `docs/PROJECT.md` (when
   architecture/data model/scope changes), `CHANGELOG.md` (under `Unreleased`), and
   the README when user-facing behavior changes.
7. **Open a PR against `main`** with `gh pr create`, fill in the Definition of Done
   checklist, and **stop there** — a human reviews and merges. Do not self-merge.

## When in doubt

Ask before building. If a requirement, interface, or design decision is unclear, or
a change would alter scope or a user-facing contract, raise it in an issue or the PR
description rather than guessing (`AGENTS.md` §11).
