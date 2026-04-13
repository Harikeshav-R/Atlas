import { AtlasError } from '@atlas/shared';
import type { BudgetLimits } from './types.ts';

export interface BudgetUsage {
  readonly tokens: number;
  readonly costMilliUsd: number;
  readonly wallClockMs: number;
  readonly toolCalls: number;
}

export class BudgetTracker {
  private tokens = 0;
  private costMilliUsd = 0;
  private toolCalls = 0;
  private readonly startedAt: number;

  constructor(private readonly limits: BudgetLimits, now: () => number) {
    this.startedAt = now();
    this.nowFn = now;
  }
  private readonly nowFn: () => number;

  addTokens(n: number): void {
    this.tokens += n;
    this.check();
  }

  addCost(milliUsd: number): void {
    this.costMilliUsd += milliUsd;
    this.check();
  }

  recordToolCall(): void {
    this.toolCalls += 1;
    this.check();
  }

  usage(): BudgetUsage {
    return {
      tokens: this.tokens,
      costMilliUsd: this.costMilliUsd,
      wallClockMs: this.nowFn() - this.startedAt,
      toolCalls: this.toolCalls,
    };
  }

  check(): void {
    const u = this.usage();
    if (u.tokens > this.limits.maxTokens) {
      throw new AtlasError('BUDGET_EXCEEDED', 'token budget exceeded', { reason: 'tokens', ...u });
    }
    if (u.costMilliUsd > this.limits.maxCostMilliUsd) {
      throw new AtlasError('BUDGET_EXCEEDED', 'cost budget exceeded', { reason: 'cost', ...u });
    }
    if (u.wallClockMs > this.limits.maxWallClockMs) {
      throw new AtlasError('BUDGET_EXCEEDED', 'wall-clock budget exceeded', { reason: 'timeout', ...u });
    }
    if (u.toolCalls > this.limits.maxToolCalls) {
      throw new AtlasError('BUDGET_EXCEEDED', 'tool-call budget exceeded', { reason: 'tool_calls', ...u });
    }
  }
}
