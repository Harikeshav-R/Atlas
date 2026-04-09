import { McpServer } from '@modelcontextprotocol/sdk/server/mcp.js';

/**
 * `atlas-web` MCP server — rate-limited web search and fetch. All returned
 * content must be wrapped with `wrapUntrusted` before reaching a model.
 */
export function createServer(): McpServer {
  const server = new McpServer({ name: 'atlas-web', version: '0.0.0' });
  // TODO: search, fetch (wrapped as untrusted_content)
  return server;
}
