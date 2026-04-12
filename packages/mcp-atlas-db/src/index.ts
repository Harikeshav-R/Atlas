import { McpServer } from '@modelcontextprotocol/sdk/server/mcp.js';
import type { AtlasDb } from '@atlas/db';
import { queries } from '@atlas/db';
import { z } from 'zod';

export interface DbServerDeps {
  readonly db: AtlasDb;
}

/**
 * `atlas-db` MCP server — narrow, parameterized tools for reading Atlas
 * persistent state. Never expose raw SQL. See technical-design.md Section 6.
 */
export function createServer(deps: DbServerDeps): McpServer {
  const server = new McpServer({ name: 'atlas-db', version: '0.0.0' });

  server.tool(
    'get_profile',
    'Get the canonical user profile',
    { profile_id: z.string() },
    async ({ profile_id }) => {
      try {
        const profile = queries.getProfile(deps.db, profile_id);
        if (!profile) {
          return { isError: true, content: [{ type: 'text', text: `Profile ${profile_id} not found` }] };
        }
        return {
          content: [{ type: 'text', text: JSON.stringify(profile) }]
        };
      } catch (e: any) {
        return { isError: true, content: [{ type: 'text', text: e.message }] };
      }
    }
  );

  server.tool(
    'write_trace_event',
    'Write a trace event for a run (harness only)',
    { 
      event_id: z.string(),
      run_id: z.string(),
      parent_event_id: z.string().optional(),
      step_index: z.number(),
      timestamp: z.string(),
      type: z.string(),
      actor: z.string().optional(),
      payload_json: z.string().optional(),
      cost_usd: z.number().optional(),
      duration_ms: z.number().optional()
    },
    async (args) => {
      try {
        queries.insertTraceEvent(deps.db, {
          event_id: args.event_id,
          run_id: args.run_id,
          parent_event_id: args.parent_event_id,
          step_index: args.step_index,
          timestamp: args.timestamp,
          type: args.type,
          actor: args.actor,
          payload_json: args.payload_json,
          cost_usd: args.cost_usd,
          duration_ms: args.duration_ms
        });
        return { content: [{ type: 'text', text: 'Success' }] };
      } catch (e: any) {
        return { isError: true, content: [{ type: 'text', text: e.message }] };
      }
    }
  );

  return server;
}
