# Coding CLI Reference

Headless / non-interactive usage docs for the coding CLIs Atlas can drive as AI backends.
These are transcribed from each tool's official documentation and are the source of truth
for [Appendix A of the design doc](../PROJECT.md#appendix-a--coding-cli-adapter-reference).

**Key takeaway:** all three support `--output-format json` plus a JSON-schema flag, so
Atlas's structured-output contract maps uniformly onto every backend.

| Doc | CLI | Role in Atlas |
|---|---|---|
| [claude-code.md](./claude-code.md) | `claude -p` | **Default CLI backend** (Phase 0) |
| [codex.md](./codex.md) | `codex exec` | Optional CLI backend |
| [antigravity.md](./antigravity.md) | `agy -p` | Optional CLI backend |

## Sources

Original source material is kept under [`sources/`](./sources/):

- `antigravity-headless.pdf` — the original Antigravity headless-mode PDF that
  `antigravity.md` was transcribed from.

The Claude Code and Codex docs were transcribed from their official web documentation.
