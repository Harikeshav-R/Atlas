import { newId, now, type Result, ok, err, AtlasError, type AtlasErrorJSON } from '@atlas/shared';
import { BudgetTracker } from './budget.ts';
import type { AgentDefinition, RunContext } from './types.ts';
import { z } from 'zod';

export interface RunOptions {
  readonly mode?: 'normal' | 'dry-run' | 'eval';
  readonly killSwitch?: () => boolean;
  readonly fakes?: {
    modelFn: (iteration: number, lastError?: string) => Promise<ModelResponse>;
    mcpCallFn: (toolName: string, args: unknown) => Promise<unknown>;
    mcpTools?: ReadonlyMap<string, { schema: z.ZodTypeAny }>;
  };
  readonly onTraceEvent?: (event: TraceEvent) => void;
}

export type ModelResponse = 
  | { type: 'text'; text: string; costMilliUsd: number; tokens: number }
  | { type: 'tool_call'; toolName: string; args: unknown; costMilliUsd: number; tokens: number };

export interface TraceEvent {
  type: 'run_started' | 'model_call' | 'tool_call' | 'error' | 'run_finished';
  timestamp: string;
  payload?: unknown;
}

export interface RunResult {
  readonly runId: string;
  readonly output: unknown;
  readonly status: 'succeeded' | 'killed' | 'budget_exhausted' | 'failed' | 'timeout';
}

/**
 * The agent harness entrypoint.
 * Fake implementation per Phase 0 Step 0.5 requirements.
 */
export async function runAgent(
  agent: AgentDefinition,
  input: unknown,
  options?: RunOptions,
): Promise<Result<RunResult, AtlasErrorJSON>> {
  const ctx: RunContext = { runId: newId('run'), agent };
  const budget = new BudgetTracker(agent.budgets, now);
  const killSwitch = options?.killSwitch ?? (() => false);
  const onTrace = options?.onTraceEvent ?? (() => {});

  onTrace({ type: 'run_started', timestamp: new Date(now()).toISOString(), payload: { input } });

  let iteration = 0;
  const maxIterations = 50; 
  let lastError: string | undefined = undefined;

  try {
    while (iteration < maxIterations) {
      if (killSwitch()) {
        onTrace({ type: 'run_finished', timestamp: new Date(now()).toISOString(), payload: { runId: ctx.runId, status: 'killed' } });
        return ok({ runId: ctx.runId, output: null, status: 'killed' });
      }

      budget.check();

      if (!options?.fakes) {
        throw new AtlasError('INTERNAL', 'Real implementation not wired yet. Use fakes.');
      }

      const response = await options.fakes.modelFn(iteration, lastError);
      
      budget.addTokens(response.tokens);
      budget.addCost(response.costMilliUsd);

      onTrace({ type: 'model_call', timestamp: new Date(now()).toISOString(), payload: response });

      if (response.type === 'text') {
        onTrace({ type: 'run_finished', timestamp: new Date(now()).toISOString(), payload: { runId: ctx.runId, status: 'succeeded', output: response.text } });
        return ok({ runId: ctx.runId, output: response.text, status: 'succeeded' });
      }

      if (response.type === 'tool_call') {
        budget.recordToolCall();
        
        if (!agent.toolAllowlist.includes(response.toolName)) {
           lastError = `Tool ${response.toolName} not in allowlist`;
           onTrace({ type: 'error', timestamp: new Date(now()).toISOString(), payload: { error: lastError } });
           iteration++;
           continue;
        }

        const toolDef = options.fakes.mcpTools?.get(response.toolName);
        if (toolDef) {
          const parsed = toolDef.schema.safeParse(response.args);
          if (!parsed.success) {
            lastError = `Schema validation failed: ${parsed.error.message}`;
            onTrace({ type: 'error', timestamp: new Date(now()).toISOString(), payload: { error: lastError } });
            iteration++;
            continue;
          }
        }

        try {
          const toolResult = await options.fakes.mcpCallFn(response.toolName, response.args);
          onTrace({ type: 'tool_call', timestamp: new Date(now()).toISOString(), payload: { toolName: response.toolName, result: toolResult } });
          lastError = undefined; 
        } catch (e: unknown) {
          const message = e instanceof Error ? e.message : String(e);
          lastError = `Tool execution failed: ${message}`;
          onTrace({ type: 'error', timestamp: new Date(now()).toISOString(), payload: { error: lastError } });
        }
      }
      
      iteration++;
    }
    
    onTrace({ type: 'run_finished', timestamp: new Date(now()).toISOString(), payload: { status: 'failed', reason: 'max_iterations' } });
    return ok({ runId: ctx.runId, output: null, status: 'failed' });

  } catch (e: unknown) {
    if (e instanceof AtlasError && e.code === 'BUDGET_EXCEEDED') {
      const isTimeout = e.message.includes('wall-clock');
      const status = isTimeout ? 'timeout' : 'budget_exhausted';
      onTrace({ type: 'run_finished', timestamp: new Date(now()).toISOString(), payload: { status } });
      return ok({ runId: ctx.runId, output: null, status });
    }
    const message = e instanceof Error ? e.message : String(e);
    onTrace({ type: 'run_finished', timestamp: new Date(now()).toISOString(), payload: { status: 'failed', error: message } });
    const eJson = e instanceof AtlasError ? e.toJSON() : { name: 'AtlasError', code: 'INTERNAL', message } as AtlasErrorJSON;
    return err(eJson);
  }
}

