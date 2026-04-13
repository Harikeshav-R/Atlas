import { describe, it, expect } from 'vitest';
import { runAgent, type RunOptions, type TraceEvent } from './runner.ts';
import type { AgentDefinition } from './types.ts';
import { z } from 'zod';

describe('Agent Harness', () => {
  const agentDef: AgentDefinition = {
    name: 'test-agent',
    systemPrompt: 'You are a test agent.',
    toolAllowlist: ['echo', 'do_something'],
    stage: 'triage',
    budgets: {
      maxTokens: 1000,
      maxCostMilliUsd: 100,
      maxWallClockMs: 5000,
      maxToolCalls: 5,
    },
  };

  it('completes on text response', async () => {
    const traces: TraceEvent[] = [];
    const opts: RunOptions = {
      fakes: {
        modelFn: async () => ({ type: 'text', text: 'Done', costMilliUsd: 0, tokens: 0 }),
        mcpCallFn: async () => null,
      },
      onTraceEvent: (e) => traces.push(e),
    };

    const res = await runAgent(agentDef, {}, opts);
    expect(res.ok).toBe(true);
    if (res.ok) {
      expect(res.data.status).toBe('succeeded');
      expect(res.data.output).toBe('Done');
    }

    expect(traces.map(t => t.type)).toEqual(['run_started', 'model_call', 'run_finished']);
  });

  it('handles tool scoping (blocks unallowed tool)', async () => {
    let callCount = 0;
    const opts: RunOptions = {
      fakes: {
        modelFn: async (_iteration, lastErr) => {
          if (callCount === 0) {
            callCount++;
            return { type: 'tool_call', toolName: 'bad_tool', args: {}, costMilliUsd: 0, tokens: 0 };
          }
          expect(lastErr).toContain('not in allowlist');
          return { type: 'text', text: 'I fixed it', costMilliUsd: 0, tokens: 0 };
        },
        mcpCallFn: async () => { throw new Error('should not be called'); },
      },
    };

    const res = await runAgent(agentDef, {}, opts);
    expect(res.ok).toBe(true);
    if (res.ok) {
      expect(res.data.status).toBe('succeeded');
    }
  });

  it('handles schema-feedback retries', async () => {
    let callCount = 0;
    const mcpTools = new Map([
      ['echo', { schema: z.object({ msg: z.string() }) }]
    ]);

    const opts: RunOptions = {
      fakes: {
        modelFn: async (_iteration, lastErr) => {
          if (callCount === 0) {
            callCount++;
            return { type: 'tool_call', toolName: 'echo', args: { wrong_field: 123 }, costMilliUsd: 0, tokens: 0 };
          }
          expect(lastErr).toContain('Schema validation failed');
          return { type: 'text', text: 'Ok', costMilliUsd: 0, tokens: 0 };
        },
        mcpCallFn: async () => null,
        mcpTools,
      },
    };

    await runAgent(agentDef, {}, opts);
  });

  it('enforces kill switch', async () => {
    const opts: RunOptions = {
      killSwitch: () => true,
      fakes: {
        modelFn: async () => ({ type: 'text', text: 'Should not run', costMilliUsd: 0, tokens: 0 }),
        mcpCallFn: async () => null,
      },
    };
    const res = await runAgent(agentDef, {}, opts);
    expect(res.ok).toBe(true);
    if (res.ok) expect(res.data.status).toBe('killed');
  });

  it('enforces budgets (tool calls)', async () => {
    const opts: RunOptions = {
      fakes: {
        modelFn: async () => ({ type: 'tool_call', toolName: 'echo', args: {}, costMilliUsd: 0, tokens: 0 }),
        mcpCallFn: async () => null,
      },
    };
    const res = await runAgent(agentDef, {}, opts);
    expect(res.ok).toBe(true);
    if (res.ok) expect(res.data.status).toBe('budget_exhausted'); // exceeded 5 tool calls
  });
});
