import { McpServer } from '@modelcontextprotocol/sdk/server/mcp.js';

/**
 * `atlas-user` MCP server — human-in-the-loop primitives.
 * `request_approval` is the canonical gating mechanism for irreversible
 * actions. See technical-design.md Section 11.
 */
export function createServer(): McpServer {
  const server = new McpServer({ name: 'atlas-user', version: '0.0.0' });
  // TODO: ask_user, request_approval, notify_user
  return server;
}
