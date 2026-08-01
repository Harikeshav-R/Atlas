# Scope & Principles

The short version of what Atlas is, so a change can be judged as in- or out-of-scope quickly.
Full detail: [PROJECT.md §1–§2](../PROJECT.md#1-vision--summary).

## What Atlas is

A **local-first, terminal-native (TUI + CLI)** job-application co-pilot for software
engineers. It discovers matching jobs, tailors a one-page resume and cover letter per posting
from a single **master resume**, drafts application-form answers, and tracks applications
through to offer — driven by AI that runs through either a **coding CLI** (Claude Code,
Codex, Antigravity) or a hosted **API** (via LiteLLM).

## Core principles (do not violate without an explicit decision)

1. **Local-first & private.** All user data stays on the machine. Data leaves only to the AI
   backend the user chose. No Atlas cloud.
2. **Bring-your-own-AI.** The AI layer is a pluggable `LLMProvider`. CLI backends are the
   default; API backends (LiteLLM) are first-class. Never hardcode a single vendor.
3. **Human-in-the-loop for anything outward-facing.** Atlas prepares; the user submits.
4. **Truth-anchored tailoring.** Tailored content derives from the master resume; the
   honesty controls + deterministic safety nets (PROJECT.md §11, §5.7) always run.
5. **Explainable.** Every match score and tailoring decision carries a rationale.

## Hard boundaries (out of scope — see PROJECT.md §2.2)

- **No auto-submission** of applications, ever. No automated logins to job boards.
- **No storing job-board credentials.** No scraping that requires logging in as the user.
- Mainstream-board scraping (LinkedIn/Indeed) is **off by default**, flag-gated, ToS-risky.
- Not a recruiter tool; not a resume-from-scratch writer; no web/mobile UI in this scope.
- **One** master resume per user (many profiles). Not multiple master resumes.
- Interview-prep assistance is out of scope for now.

## When a change touches scope

If a task would cross a boundary above, change the data model, or alter a user-facing
contract: **stop and ask** (AGENTS.md §11), or surface it in the PR for guidance. Update
[PROJECT.md](../PROJECT.md) in the same PR when scope/architecture genuinely changes.
