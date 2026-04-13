# 08 — Reference

> Quick-reference tables, the out-of-scope list, and the glossary. Reach for this doc when you need a lookup but not deep context.

---

## 1. Agents and their primary tools

| Agent | Stage | Primary tools | Typical budget |
|---|---|---|---|
| Profile Parser | generation | atlas-fs, atlas-profile | 2 steps, $0.10 |
| Discovery (generic) | navigation | playwright, atlas-db, atlas-web | 15 steps, $0.30 |
| Triage | triage | atlas-db, atlas-profile | 1 step, $0.02 |
| Evaluation | evaluation | atlas-db, atlas-web, atlas-profile, playwright.get_text | 20 steps, $0.50 |
| CV Tailor | generation | atlas-profile, atlas-db.read_evaluation | 3 steps, $0.15 |
| Cover Letter | generation | atlas-profile, atlas-db.read_evaluation, atlas-stories | 3 steps, $0.15 |
| Honesty Verifier | verification | atlas-profile, atlas-db.read_generated_asset | 2 steps, $0.10 |
| Application | navigation | playwright, atlas-profile, atlas-stories, atlas-user | 40 steps, $0.80 |
| Story Bank Interview | interaction | atlas-user, atlas-profile, atlas-db | 30 steps, $0.50 |
| Negotiation | generation | atlas-db, atlas-web, atlas-profile, atlas-user | 10 steps, $0.40 |
| Rejection Analyst | evaluation | atlas-db | 5 steps, $0.20 |

For details on each agent, see the relevant subsystem doc:
- Profile Parser → `docs/05-subsystems-discovery-evaluation-generation.md §1`
- Discovery, Triage, Evaluation → `docs/05-subsystems-discovery-evaluation-generation.md §2–3`
- CV Tailor, Cover Letter, Honesty Verifier → `docs/05-subsystems-discovery-evaluation-generation.md §4`
- Application → `docs/06-subsystems-application-stories-negotiation.md §1`
- Story Bank Interview → `docs/06-subsystems-application-stories-negotiation.md §2`
- Negotiation → `docs/06-subsystems-application-stories-negotiation.md §3`

For agent definition format and the harness contract, see `docs/02-agent-runtime.md §3`.

---

## 2. Application status state machine

```
discovered → evaluated → shortlisted → applied → screening → interviewing → offer → accepted
                     ↓              ↓        ↓          ↓           ↓           ↓
                  archived       dropped  rejected  rejected   rejected   rejected  withdrawn
```

Transitions are enforced by the `atlas-db.update_application_status` tool; invalid transitions return an error.

---

## 3. Default budgets summary

- Per-run: varies per agent, see table above
- Global monthly: $20 default, user-configurable
- Global concurrent runs: 4 default
- Per-agent concurrent: 2 default
- Per-portal concurrent application runs: 1 (hard limit)

---

## 4. File size limits

- Profile upload: 10 MB
- HTML snapshot: 5 MB (larger = truncated)
- Trace event payload (inline): 4 KB (larger = offloaded to blob store)
- Tool text response: 50 KB (larger = truncated with offset hint)

---

## 5. Out of scope for v1

Intentionally not in the initial build. Revisit after Phase 5 (see `product-plan.md` for phases).

- Multi-user support
- Cloud sync across devices
- Mobile apps
- Interview scheduling integration
- Calendar integration
- Direct ATS API submission (without browser automation)
- AI-generated portfolio pieces
- Reference management
- Salary negotiation with live bot-to-bot
- Localization beyond the Profile Parser Agent
- Voice interface
- Analytics on hiring pipelines (employer-side)

---

## 6. Glossary

- **Agent.** A declarative configuration of system prompt + tool allowlist + default model + budgets. Instantiated per run by the harness. See `docs/02-agent-runtime.md §3`.
- **Approval.** A user response to an agent request via `atlas-user.request_approval`. Required for gated tools. See `docs/02-agent-runtime.md §11`.
- **Canonical profile.** The YAML document that is the single source of truth for the user's self-description, produced by the Profile Parser Agent from whatever format they uploaded. See `docs/05-subsystems-discovery-evaluation-generation.md §1`.
- **Drizzle.** The TypeScript ORM Atlas uses for SQLite. See `docs/03-persistence.md §2`.
- **Evaluation.** The structured 6-block reasoning produced by the Evaluation Agent. See `docs/05-subsystems-discovery-evaluation-generation.md §3` and `product-plan.md`.
- **Fixture.** A saved input + expected outcome used for agent evaluation. See `docs/02-agent-runtime.md §13`.
- **Gated tool.** A tool that requires a prior approval event in the run trace to be callable. See `docs/02-agent-runtime.md §1` (point 4).
- **Harness.** The code that runs an agent: enforces budgets, captures traces, scopes tools, gates approvals, handles kill signals. See `docs/02-agent-runtime.md §1`.
- **HITL.** Human-in-the-loop. The default mode where irreversible actions require explicit user approval.
- **MCP.** Model Context Protocol. A standard interface for tools that LLM agents call. See `docs/02-agent-runtime.md §6`.
- **Model Router.** The wrapper around the Vercel AI SDK that handles provider differences and stage-based routing. See `docs/02-agent-runtime.md §4`.
- **Run.** A single agent invocation with its trace, budget, and result. See `docs/02-agent-runtime.md §1`.
- **Scope.** A structured string identifying what an approval authorizes, used by the harness to gate tool calls. See `docs/02-agent-runtime.md §11`.
- **Stage.** A category of model use (triage, evaluation, generation, verification, navigation, interaction). Users map stages to models. See `docs/02-agent-runtime.md §4`.
- **Trace.** The sequence of events that happened during a run. The unit of debugging. See `docs/02-agent-runtime.md §10`.
- **ULID.** The ID format Atlas uses everywhere — sortable, prefixed, lexicographic. See `docs/01-foundations.md §3`.
- **Untrusted content.** Any text from outside Atlas (scraped pages, user files, JD content) that must be wrapped in `<untrusted_content>` markers before reaching a model. See `docs/02-agent-runtime.md §12`.
- **YOLO.** A scoped opt-in mode where approvals are auto-granted after a visible delay, for batch efficiency. See `docs/06-subsystems-application-stories-negotiation.md §1`.
