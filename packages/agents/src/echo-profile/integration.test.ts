import { describe, it, expect, beforeEach } from 'vitest';
import { createServer as createDbServer } from '@atlas/mcp-atlas-db';
import { createDb, queries, type AtlasDb } from '@atlas/db';
import { runAgent, type RunOptions } from '@atlas/harness';
import { echoProfileAgent } from './definition.ts';
import { Client } from '@modelcontextprotocol/sdk/client/index.js';
import { InMemoryTransport } from '@modelcontextprotocol/sdk/inMemory.js';
import { z } from 'zod';

describe('echo-profile agent', () => {
  let db: AtlasDb;

  beforeEach(() => {
    db = createDb(':memory:');
    // Seed a fake profile in the DB
    queries.insertProfile(db, {
      profile_id: 'prof_test',
      yaml_blob: 'name: Alice',
      parsed_json: '{"name":"Alice"}',
      version: 1,
      schema_version: 1,
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    });
    queries.insertRun(db, {
      run_id: 'run_test_echo',
      agent_name: 'echo-profile',
      mode: 'normal',
      started_at: new Date().toISOString(),
      status: 'running',
    });
  });

  it('runs end-to-end via the fake harness, reads the profile, and returns the name', async () => {
    const dbServer = createDbServer({ db });
    const [clientTransport, serverTransport] = InMemoryTransport.createLinkedPair();
    await dbServer.connect(serverTransport);
    
    const dbClient = new Client({ name: 'test-client', version: '1.0.0' }, { capabilities: {} });
    await dbClient.connect(clientTransport);

    let modelCalls = 0;

    const opts: RunOptions = {
      fakes: {
        modelFn: async () => {
          if (modelCalls === 0) {
            modelCalls++;
            return {
              type: 'tool_call',
              toolName: 'get_profile',
              args: { profile_id: 'prof_test' },
              costMilliUsd: 10,
              tokens: 150
            };
          }
          // On second call, pretend the model has parsed the result and returns the name
          return { type: 'text', text: 'Alice', costMilliUsd: 5, tokens: 50 };
        },
        mcpCallFn: async (toolName, args) => {
          const result = await dbClient.callTool({ name: toolName, arguments: args as Record<string, unknown> });
          const content = result.content as Array<{ type: string; text?: string }>;
          if (result.isError) throw new Error(String(content[0]?.text || 'error'));
          return result;
        },
        mcpTools: new Map([
          ['get_profile', { schema: z.object({ profile_id: z.string() }) }]
        ])
      }
    };

    const res = await runAgent(echoProfileAgent, { profile_id: 'prof_test' }, opts);
    
    expect(res.ok).toBe(true);
    if (res.ok) {
      expect(res.data.status).toBe('succeeded');
      expect(res.data.output).toBe('Alice');
    }

    await dbClient.close();
    await dbServer.close();
  });
});
