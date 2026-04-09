import type { PrefixedId } from '@atlas/shared';

export interface BudgetLimits {
  readonly maxTokens: number;
  readonly maxCostMilliUsd: number;
  readonly maxWallClockMs: number;
  readonly maxToolCalls: number;
}

export interface AgentDefinition {
  readonly name: string;
  readonly systemPrompt: string;
  readonly toolAllowlist: readonly string[];
  readonly stage: 'triage' | 'evaluation' | 'generation' | 'verification' | 'navigation' | 'interaction';
  readonly budgets: BudgetLimits;
}

export interface RunContext {
  readonly runId: PrefixedId<'run'>;
  readonly agent: AgentDefinition;
}
