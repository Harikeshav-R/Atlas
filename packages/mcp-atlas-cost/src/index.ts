import { McpServer } from '@modelcontextprotocol/sdk/server/mcp.js';

/**
 * `atlas-cost` MCP server — budget introspection for agents. Lets an agent
 * ask "how much budget do I have left?" without granting write access.
 */
export function createServer(): McpServer {
  const server = new McpServer({ name: 'atlas-cost', version: '0.0.0' });
  // TODO: get_remaining_budget, get_run_cost
  return server;
}
