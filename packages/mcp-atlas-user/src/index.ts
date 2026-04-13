import { McpServer } from '@modelcontextprotocol/sdk/server/mcp.js';
import { z } from 'zod';
import { newId } from '@atlas/shared';
import type { AtlasDb } from '@atlas/db';
import { queries } from '@atlas/db';

export interface UserServerDeps {
  readonly db: AtlasDb;
  readonly requestUserApproval: (approvalId: string) => Promise<{ status: string, responseNote?: string }>;
  readonly askUser: (question: string) => Promise<string>;
  readonly notifyUser: (message: string, level: string) => void;
}

/**
 * `atlas-user` MCP server — human-in-the-loop primitives.
 * `request_approval` is the canonical gating mechanism for irreversible
 * actions. See technical-design.md Section 11.
 */
export function createServer(deps: UserServerDeps): McpServer {
  const server = new McpServer({ name: 'atlas-user', version: '0.0.0' });

  server.registerTool(
    'request_approval',
    {
      description: 'Request user approval for a gated action',
      inputSchema: {
        run_id: z.string(),
        scope: z.string(),
        title: z.string(),
        description: z.string(),
        screenshot_path: z.string().optional(),
        options: z.array(z.string())
      }
    },
    async (args) => {
      const approval_id = newId('approval');
      const now = new Date().toISOString();
      const timeout_at = new Date(Date.now() + 24 * 60 * 60 * 1000).toISOString();
      
      queries.insertApproval(deps.db, {
        approval_id,
        run_id: args.run_id,
        scope: args.scope,
        title: args.title,
        description: args.description,
        screenshot_path: args.screenshot_path,
        options_json: JSON.stringify(args.options),
        status: 'pending',
        requested_at: now,
        timeout_at
      });

      try {
        const result = await deps.requestUserApproval(approval_id);
        
        const ValidStatusSchema = z.enum(['pending', 'granted', 'denied', 'timed_out']);
        const validStatus = ValidStatusSchema.parse(result.status);

        queries.updateApprovalResponse(
          deps.db, 
          approval_id, 
          validStatus, 
          JSON.stringify(result), 
          new Date().toISOString()
        );

        return {
          content: [{ type: 'text', text: JSON.stringify(result) }]
        };
      } catch (e: unknown) {
        const message = e instanceof Error ? e.message : String(e);
        return { isError: true, content: [{ type: 'text', text: message }] };
      }
    }
  );

  server.registerTool(
    'ask',
    {
      description: 'Ask the user a question',
      inputSchema: { question: z.string() }
    },
    async ({ question }) => {
      try {
        const response = await deps.askUser(question);
        return { content: [{ type: 'text', text: response }] };
      } catch (e: unknown) {
        const message = e instanceof Error ? e.message : String(e);
        return { isError: true, content: [{ type: 'text', text: message }] };
      }
    }
  );

  server.registerTool(
    'notify',
    {
      description: 'Send a desktop notification to the user',
      inputSchema: { message: z.string(), level: z.string().default('info') }
    },
    async ({ message, level }) => {
      try {
        deps.notifyUser(message, level);
        return { content: [{ type: 'text', text: 'Notification sent' }] };
      } catch (e: unknown) {
        const message = e instanceof Error ? e.message : String(e);
        return { isError: true, content: [{ type: 'text', text: message }] };
      }
    }
  );

  return server;
}
