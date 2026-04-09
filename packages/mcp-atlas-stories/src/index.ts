import { McpServer } from '@modelcontextprotocol/sdk/server/mcp.js';

/**
 * `atlas-stories` MCP server — Story Bank retrieval and scoring for
 * CV/cover letter generation.
 */
export function createServer(): McpServer {
  const server = new McpServer({ name: 'atlas-stories', version: '0.0.0' });
  // TODO: search_stories, get_story, rank_stories_for_listing
  return server;
}
