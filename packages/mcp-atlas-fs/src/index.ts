import { McpServer } from '@modelcontextprotocol/sdk/server/mcp.js';
import { z } from 'zod';
import * as fs from 'node:fs/promises';
import { resolve, relative, isAbsolute } from 'node:path';
import { PDFParse } from 'pdf-parse';

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

  server.registerTool(
    'read',
    {
      description: 'Read a file from the sandboxed filesystem. Supports text and PDF extraction.',
      inputSchema: { path: z.string() }
    },
    async ({ path }) => {
      try {
        const safePath = checkSandbox(path);
        
        if (safePath.toLowerCase().endsWith('.pdf')) {
          const dataBuffer = await fs.readFile(safePath);
          const parser = new PDFParse({ data: dataBuffer });
          const data = await parser.getText();
          return { content: [{ type: 'text', text: data.text }] };
        }
        
        const text = await fs.readFile(safePath, 'utf-8');
        return { content: [{ type: 'text', text }] };
      } catch (e: unknown) {
        const message = e instanceof Error ? e.message : String(e);
        return { isError: true, content: [{ type: 'text', text: message }] };
      }
    }
  );

  return server;
}
