# Agent Documentation

Focused, task-oriented docs for coding agents (and humans) working on Atlas. These expand
on the repo-wide contract in [`AGENTS.md`](../../AGENTS.md) and the design in
[`docs/PROJECT.md`](../PROJECT.md) — they don't replace either.

> **Precedence:** [`AGENTS.md`](../../AGENTS.md) is the normative working agreement. When a
> doc here restates a rule, `AGENTS.md` wins. When it restates a design decision,
> [`PROJECT.md`](../PROJECT.md) wins. These files exist to make the *relevant slice* easy to
> find while working on a given area.

## Index

| Doc | Covers |
|---|---|
| [scope-and-principles.md](./scope-and-principles.md) | What Atlas is/isn't; the guiding principles; boundaries not to cross |
| [architecture.md](./architecture.md) | System shape, process model, module map, where code goes |
| [llm-integration.md](./llm-integration.md) | AI backends: CLI adapters + LiteLLM, structured output, prompts, retries |
| [coding-standards.md](./coding-standards.md) | Style, typing, error handling, secrets, cross-platform rules |
| [testing-strategy.md](./testing-strategy.md) | Isolation, coverage bar, markers, fakes/fixtures |
| [workflow.md](./workflow.md) | Branches, commits, PRs, definition of done (pointers to `AGENTS.md`) |

## Status

Atlas is in **design / pre-implementation**. Some docs describe target state (e.g. CI,
package layout) that Phase 0 will create. Where a doc describes something not yet built, it
says so.

## Reference

- Closest existing project reviewed as a reference: **Resume-Matcher** — see
  [PROJECT.md §19](../PROJECT.md#19-reference-projects) for what was adopted and rejected.
- Coding-CLI headless docs: [`docs/cli-reference/`](../cli-reference/).
