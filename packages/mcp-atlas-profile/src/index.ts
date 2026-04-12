import { McpServer } from '@modelcontextprotocol/sdk/server/mcp.js';
import { z } from 'zod';
import type { AtlasDb } from '@atlas/db';
import { queries } from '@atlas/db';
import { ProfileSchema } from '@atlas/schemas';
import yaml from 'yaml';

export interface ProfileServerDeps {
  readonly db: AtlasDb;
}

export function createServer(deps: ProfileServerDeps): McpServer {
  const server = new McpServer({ name: 'atlas-profile', version: '0.0.0' });

  server.registerTool(
    'read',
    {
      description: 'Read the canonical user profile',
      inputSchema: { include_private: z.boolean().default(false) }
    },
    async ({ include_private: _include_private }) => {
      try {
        const profile = queries.getProfile(deps.db, 'default');
        if (!profile) return { isError: true, content: [{ type: 'text', text: 'Profile not found' }] };
        return { content: [{ type: 'text', text: profile.yaml_blob }] };
      } catch (e: unknown) {
        const message = e instanceof Error ? e.message : String(e);
        return { isError: true, content: [{ type: 'text', text: message }] };
      }
    }
  );

  server.registerTool(
    'validate_schema',
    {
      description: 'Validate a YAML string against the canonical profile schema',
      inputSchema: { yaml_string: z.string() }
    },
    async ({ yaml_string }) => {
      try {
        const parsed = yaml.parse(yaml_string);
        const result = ProfileSchema.safeParse(parsed);
        if (!result.success) {
          return { content: [{ type: 'text', text: `Invalid schema: ${result.error.message}` }] };
        }
        return { content: [{ type: 'text', text: 'Valid schema' }] };
      } catch (e: unknown) {
        const message = e instanceof Error ? e.message : String(e);
        return { content: [{ type: 'text', text: `YAML parse error: ${message}` }] };
      }
    }
  );

  return server;
}
