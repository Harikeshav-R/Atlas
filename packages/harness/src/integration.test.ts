import { describe, it, expect, beforeEach } from 'vitest';
import { createServer as createDbServer } from '@atlas/mcp-atlas-db';
import { createServer as createUserServer } from '@atlas/mcp-atlas-user';
import { createDb, queries, approvals, type AtlasDb } from '@atlas/db';
import { runAgent, type RunOptions } from './runner.ts';
import type { AgentDefinition } from './types.ts';
import { Client } from '@modelcontextprotocol/sdk/client/index.js';
import { InMemoryTransport } from '@modelcontextprotocol/sdk/inMemory.js';

describe('Harness to MCP Integration', () => {
  let db: AtlasDb;

  beforeEach(() => {
    db = createDb(':memory:');
    queries.insertRun(db, {
      run_id: 'run_integration',
      agent_name: 'test-agent',
      mode: 'normal',
      started_at: new Date().toISOString(),
      status: 'running',
    });
  });

  it('harness -> MCP client -> server -> DB write', async () => {
    // Setup db server
    const dbServer = createDbServer({ db });
    const [dbClientTransport, dbServerTransport] = InMemoryTransport.createLinkedPair();
    await dbServer.connect(dbServerTransport);
    
    const dbClient = new Client({ name: 'test-client', version: '1.0.0' }, { capabilities: {} });
    await dbClient.connect(dbClientTransport);

    // Run harness with faked model that calls write_trace_event
    const agentDef: AgentDefinition = {
      name: 'test-agent',
      systemPrompt: '',
      toolAllowlist: ['write_trace_event'],
      stage: 'triage',
      budgets: { maxTokens: 1000, maxCostMilliUsd: 100, maxWallClockMs: 5000, maxToolCalls: 5 },
    };

    let called = false;
    const opts: RunOptions = {
      fakes: {
        modelFn: async () => {
          if (!called) {
            called = true;
            return {
              type: 'tool_call',
              toolName: 'write_trace_event',
              args: {
                event_id: 'event_integration',
                run_id: 'run_integration',
                step_index: 1,
                timestamp: new Date().toISOString(),
                type: 'tool_call'
              },
              costMilliUsd: 0,
              tokens: 0
            };
          }
          return { type: 'text', text: 'Done', costMilliUsd: 0, tokens: 0 };
        },
        mcpCallFn: async (toolName, args) => {
          const result = await dbClient.callTool({ name: toolName, arguments: args as Record<string, unknown> });
          const content = result.content as Array<{ type: string; text?: string }>;
          if (result.isError) throw new Error(String(content[0]?.type === 'text' ? content[0].text : 'error'));
          return result;
        },
      }
    };

    const res = await runAgent(agentDef, {}, opts);
    expect(res.ok).toBe(true);

    const events = queries.getTraceEventsForRun(db, 'run_integration');
    expect(events.length).toBe(1);
    expect(events[0]?.event_id).toBe('event_integration');

    // Also test mcp-atlas-user
    const userServer = createUserServer({
      db,
      requestUserApproval: async (id) => ({ status: 'granted' }),
      askUser: async () => 'yes',
      notifyUser: () => {}
    });
    const [userClientTransport, userServerTransport] = InMemoryTransport.createLinkedPair();
    await userServer.connect(userServerTransport);
    
    const userClient = new Client({ name: 'test-client-2', version: '1.0.0' }, { capabilities: {} });
    await userClient.connect(userClientTransport);

    const approvalResult = await userClient.callTool({
      name: 'request_approval',
      arguments: {
        run_id: 'run_integration',
        scope: 'test-scope',
        title: 'Title',
        description: 'Desc',
        options: ['approve', 'deny']
      }
    });

    expect(approvalResult.isError).toBeFalsy();
    
    // Ensure DB was updated
    const runApprovals = db.select().from(approvals).all();
    expect(runApprovals.length).toBe(1);
    expect(runApprovals[0]?.status).toBe('granted');
    expect(runApprovals[0]?.run_id).toBe('run_integration');

    await userClient.close();
    await userServer.close();
    await dbClient.close();
    await dbServer.close();
  });
});