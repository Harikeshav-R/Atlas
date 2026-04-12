import { McpServer } from '@modelcontextprotocol/sdk/server/mcp.js';
import { z } from 'zod';
import * as fs from 'node:fs/promises';
import { resolve } from 'node:path';
import pdf from 'pdf-parse';

export interface FsServerDeps {
  readonly allowedRoots: string[];
}

export function createServer(deps: FsServerDeps): McpServer {
  const server = new McpServer({ name: 'atlas-fs', version: '0.0.0' });

  function checkSandbox(path: string) {
    const resolved = resolve(path);
    if (!deps.allowedRoots.some(root => resolved.startsWith(root))) {
      throw new Error(`Path ${path} is outside of allowed roots`);
    }
    return resolved;
  }

  server.tool(
    'read',
    'Read a file from the sandboxed filesystem. Supports text and PDF extraction.',
    { path: z.string() },
    async ({ path }) => {
      try {
        const safePath = checkSandbox(path);
        
        if (safePath.toLowerCase().endsWith('.pdf')) {
          const dataBuffer = await fs.readFile(safePath);
          const data = await pdf(dataBuffer);
          return { content: [{ type: 'text', text: data.text }] };
        }
        
        const text = await fs.readFile(safePath, 'utf-8');
        return { content: [{ type: 'text', text }] };
      } catch (e: any) {
        return { isError: true, content: [{ type: 'text', text: e.message }] };
      }
    }
  );

  return server;
}
