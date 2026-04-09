import { McpServer } from '@modelcontextprotocol/sdk/server/mcp.js';

export interface FsServerDeps {
  /** Absolute sandbox roots. All paths passed to tools must resolve within one of these. */
  readonly sandboxRoots: readonly string[];
}

/**
 * `atlas-fs` MCP server — sandboxed read/write for documents and attachments.
 * Resolves every path against `sandboxRoots` and rejects traversal attempts.
 */
export function createServer(_deps: FsServerDeps): McpServer {
  const server = new McpServer({ name: 'atlas-fs', version: '0.0.0' });
  // TODO: read_file, write_file, list_dir, delete_file (gated)
  return server;
}
