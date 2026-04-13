import { McpServer } from '@modelcontextprotocol/sdk/server/mcp.js';
import { z } from 'zod';
import { NodeHtmlMarkdown } from 'node-html-markdown';
import { wrapUntrusted } from '@atlas/shared';
import { RateLimiter } from './rate-limiter.ts';
import { FetchCache } from './cache.ts';

const MAX_RESPONSE_SIZE = 50_000; // 50 KB text limit

function truncate(text: string, limit: number): string {
  if (text.length <= limit) return text;
  return text.slice(0, limit) + '\n\n...[truncated]';
}

function extractDomain(url: string): string {
  try {
    return new URL(url).hostname;
  } catch {
    return 'unknown';
  }
}

export interface WebServerDeps {
  readonly braveApiKey?: string;
}

/**
 * `atlas-web` MCP server — rate-limited web search and fetch.
 * All returned content is wrapped with `wrapUntrusted`.
 */
export function createServer(deps: WebServerDeps = {}): McpServer {
  const server = new McpServer({ name: 'atlas-web', version: '0.1.0' });
  const rateLimiter = new RateLimiter();
  const cache = new FetchCache();
  const nhm = new NodeHtmlMarkdown();

  server.tool(
    'search',
    'Search the web using DuckDuckGo HTML or Brave Search API. Returns results as markdown. Use for comp research, company info, or verifying claims. This makes a network request.',
    {
      query: z.string().min(1).describe('The search query'),
      limit: z.number().int().min(1).max(20).default(5).describe('Max number of results to return'),
    },
    async ({ query, limit }) => {
      try {
        const results = deps.braveApiKey
          ? await searchBrave(query, limit, deps.braveApiKey, rateLimiter)
          : await searchDuckDuckGo(query, limit, rateLimiter);

        const markdown = results
          .map((r, i) => `${i + 1}. [${r.title}](${r.url})\n   ${r.snippet}`)
          .join('\n\n');

        return {
          content: [{
            type: 'text' as const,
            text: wrapUntrusted(truncate(markdown, MAX_RESPONSE_SIZE), 'web_search', query),
          }],
        };
      } catch (error) {
        const message = error instanceof Error ? error.message : 'Unknown search error';
        return {
          content: [{ type: 'text' as const, text: JSON.stringify({ ok: false, error: { code: 'search.failed', message } }) }],
          isError: true,
        };
      }
    },
  );

  server.tool(
    'fetch',
    'Fetch a URL and return its content as extracted markdown. Use for reading job descriptions, company pages, salary data. For pages requiring JS execution or interaction, use playwright tools instead. This makes a network request.',
    {
      url: z.string().url().describe('The URL to fetch'),
    },
    async ({ url }) => {
      try {
        const cached = cache.get(url);
        if (cached) {
          return {
            content: [{ type: 'text' as const, text: wrapUntrusted(cached, 'fetched_page', url) }],
          };
        }

        const domain = extractDomain(url);
        await rateLimiter.waitForDomain(domain);

        const response = await fetch(url, {
          headers: {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
          },
          signal: AbortSignal.timeout(15_000),
        });

        if (!response.ok) {
          return {
            content: [{ type: 'text' as const, text: JSON.stringify({ ok: false, error: { code: 'fetch.http_error', message: `HTTP ${response.status}` } }) }],
            isError: true,
          };
        }

        const html = await response.text();
        const markdown = nhm.translate(html);
        const truncated = truncate(markdown, MAX_RESPONSE_SIZE);

        cache.set(url, truncated);

        return {
          content: [{ type: 'text' as const, text: wrapUntrusted(truncated, 'fetched_page', url) }],
        };
      } catch (error) {
        const message = error instanceof Error ? error.message : 'Unknown fetch error';
        return {
          content: [{ type: 'text' as const, text: JSON.stringify({ ok: false, error: { code: 'fetch.failed', message } }) }],
          isError: true,
        };
      }
    },
  );

  return server;
}

interface SearchResult {
  readonly title: string;
  readonly url: string;
  readonly snippet: string;
}

async function searchDuckDuckGo(
  query: string,
  limit: number,
  rateLimiter: RateLimiter,
): Promise<readonly SearchResult[]> {
  await rateLimiter.waitForDomain('html.duckduckgo.com');

  const params = new URLSearchParams({ q: query });
  const response = await fetch(`https://html.duckduckgo.com/html/?${params.toString()}`, {
    headers: {
      'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
      'Accept': 'text/html',
    },
    signal: AbortSignal.timeout(10_000),
  });

  if (!response.ok) {
    throw new Error(`DuckDuckGo returned HTTP ${response.status}`);
  }

  const html = await response.text();
  return parseDuckDuckGoResults(html, limit);
}

function parseDuckDuckGoResults(html: string, limit: number): readonly SearchResult[] {
  const results: SearchResult[] = [];

  // DuckDuckGo HTML results have a consistent pattern:
  // <a class="result__a" href="...">title</a>
  // <a class="result__snippet">snippet</a>
  const resultPattern = /<a[^>]+class="result__a"[^>]+href="([^"]*)"[^>]*>([\s\S]*?)<\/a>/gi;
  const snippetPattern = /<a[^>]+class="result__snippet"[^>]*>([\s\S]*?)<\/a>/gi;

  const titleMatches = [...html.matchAll(resultPattern)];
  const snippetMatches = [...html.matchAll(snippetPattern)];

  for (let i = 0; i < Math.min(titleMatches.length, limit); i++) {
    const titleMatch = titleMatches[i];
    const snippetMatch = snippetMatches[i];
    if (!titleMatch) continue;

    let url = titleMatch[1] ?? '';
    // DuckDuckGo wraps URLs in redirects; extract the actual URL
    const uddgMatch = url.match(/uddg=([^&]+)/);
    if (uddgMatch?.[1]) {
      url = decodeURIComponent(uddgMatch[1]);
    }

    const title = (titleMatch[2] ?? '').replace(/<[^>]*>/g, '').trim();
    const snippet = snippetMatch
      ? (snippetMatch[1] ?? '').replace(/<[^>]*>/g, '').trim()
      : '';

    if (url && title) {
      results.push({ title, url, snippet });
    }
  }

  return results;
}

async function searchBrave(
  query: string,
  limit: number,
  apiKey: string,
  rateLimiter: RateLimiter,
): Promise<readonly SearchResult[]> {
  await rateLimiter.waitForDomain('api.search.brave.com');

  const params = new URLSearchParams({ q: query, count: String(limit) });
  const response = await fetch(`https://api.search.brave.com/res/v1/web/search?${params.toString()}`, {
    headers: {
      'X-Subscription-Token': apiKey,
      'Accept': 'application/json',
    },
    signal: AbortSignal.timeout(10_000),
  });

  if (!response.ok) {
    throw new Error(`Brave Search returned HTTP ${response.status}`);
  }

  const data = await response.json() as {
    web?: { results?: Array<{ title: string; url: string; description: string }> };
  };

  return (data.web?.results ?? []).slice(0, limit).map((r) => ({
    title: r.title,
    url: r.url,
    snippet: r.description,
  }));
}
