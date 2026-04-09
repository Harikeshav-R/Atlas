import { McpServer } from '@modelcontextprotocol/sdk/server/mcp.js';

/**
 * `atlas-profile` MCP server — read/write the canonical profile YAML.
 * See technical-design.md Section 6 and 22.
 */
export function createServer(): McpServer {
  const server = new McpServer({ name: 'atlas-profile', version: '0.0.0' });
  // TODO: get_profile, update_profile_section, get_story_candidates
  return server;
}
