# Contributing to Atlas

Thank you for your interest in contributing to Project Atlas! 

We welcome contributions of all kinds, including bug fixes, new features, documentation improvements, and more.

## Source of Truth

Before making any changes, please familiarize yourself with the core architecture and rules of this project:

1. **`PRODUCT_PLAN.md`**: Understand what we are building and why.
2. **`TECHNICAL_DESIGN.md`**: The engineering design, architecture, and MCP server structures.
3. **`GEMINI.md` / `CLAUDE.md`**: The rules and patterns you must follow on every task.

## Quick Start

The repository is structured as a `pnpm` monorepo using `turbo`. 

```bash
pnpm install              # install and rebuild native modules
pnpm dev                  # run Electron in dev mode with HMR
pnpm test                 # run all tests
pnpm typecheck            # tsc across all packages
pnpm lint                 # ESLint + Prettier check
```

## Making Changes

1. **Fork the repository** and create a feature branch from `main`.
2. Ensure you adhere to the engineering standards defined in the root documentation.
3. **Write Tests**: New code must ship with tests.
4. **Before Committing**: Always run `pnpm typecheck && pnpm lint && pnpm test`.
5. **Changesets**: If your change modifies user-facing behavior or exports, run `pnpm changeset` and commit the generated file.

## Pull Requests

1. Open a Pull Request providing a clear explanation of what changed and why.
2. Ensure all CI checks (Lint, Typecheck, Test) pass.
3. Link any relevant GitHub issues.

By contributing to this project, you agree to abide by our [Code of Conduct](./CODE_OF_CONDUCT.md).
