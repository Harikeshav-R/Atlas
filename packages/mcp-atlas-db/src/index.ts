import { McpServer } from '@modelcontextprotocol/sdk/server/mcp.js';
import type { AtlasDb } from '@atlas/db';

export interface DbServerDeps {
  readonly db: AtlasDb;
}

/**
 * `atlas-db` MCP server — narrow, parameterized tools for reading Atlas
 * persistent state. Never expose raw SQL. See technical-design.md Section 6.
 */
export function createServer(_deps: DbServerDeps): McpServer {
  const server = new McpServer({ name: 'atlas-db', version: '0.0.0' });
  // TODO: register tools (get_listing, list_runs, insert_trace_event, ...)
  return server;
}
