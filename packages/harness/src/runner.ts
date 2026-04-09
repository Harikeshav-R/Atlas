import { newId, now, type Result, ok } from '@atlas/shared';
import { BudgetTracker } from './budget.ts';
import type { AgentDefinition, RunContext } from './types.ts';

export interface RunResult {
  readonly runId: string;
  readonly output: unknown;
}

/**
 * The agent harness entrypoint. Currently a stub — real implementation will
 * wire the Vercel AI SDK loop, MCP tool scoping, approval gating and trace
 * capture. See technical-design.md Section 4.
 */
export async function runAgent(
  agent: AgentDefinition,
  _input: unknown,
): Promise<Result<RunResult>> {
  const ctx: RunContext = { runId: newId('run'), agent };
  const _budget = new BudgetTracker(agent.budgets, now);
  // TODO: model-router call + tool loop + trace emission
  return ok({ runId: ctx.runId, output: null });
}
