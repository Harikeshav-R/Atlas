import type { ScraperAdapter, SourceConfig, DiscoveredListing } from '../types.ts';

const BOARDS_API_BASE = 'https://boards-api.greenhouse.io/v1/boards';

interface GreenhouseJob {
  readonly id: number;
  readonly title: string;
  readonly absolute_url: string;
  readonly location: { readonly name: string };
  readonly content?: string;
  readonly departments: ReadonlyArray<{ readonly name: string }>;
}

interface GreenhouseListResponse {
  readonly jobs: readonly GreenhouseJob[];
}

function inferRemoteModel(location: string): 'remote' | 'hybrid' | 'onsite' | 'unknown' {
  const lower = location.toLowerCase();
  if (lower.includes('remote')) return 'remote';
  if (lower.includes('hybrid')) return 'hybrid';
  return 'unknown';
}

function stripHtml(html: string): string {
  return html
    .replace(/<br\s*\/?>/gi, '\n')
    .replace(/<\/p>/gi, '\n\n')
    .replace(/<\/li>/gi, '\n')
    .replace(/<li[^>]*>/gi, '- ')
    .replace(/<\/h[1-6]>/gi, '\n\n')
    .replace(/<h[1-6][^>]*>/gi, '## ')
    .replace(/<[^>]*>/g, '')
    .replace(/&amp;/g, '&')
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>')
    .replace(/&quot;/g, '"')
    .replace(/&#39;/g, "'")
    .replace(/\n{3,}/g, '\n\n')
    .trim();
}

export class GreenhouseAdapter implements ScraperAdapter {
  readonly platform = 'greenhouse';

  async list(config: SourceConfig): Promise<readonly DiscoveredListing[]> {
    const { companySlug } = config;
    const url = `${BOARDS_API_BASE}/${encodeURIComponent(companySlug)}/jobs`;

    const response = await fetch(url, {
      headers: { Accept: 'application/json' },
      signal: AbortSignal.timeout(15_000),
    });

    if (!response.ok) {
      throw new Error(`Greenhouse API returned HTTP ${response.status} for ${companySlug}`);
    }

    const data = (await response.json()) as GreenhouseListResponse;

    return data.jobs.map((job) => ({
      canonicalUrl: this.canonicalize(job.absolute_url),
      companyName: companySlug,
      roleTitle: job.title,
      location: job.location.name || undefined,
      remoteModel: inferRemoteModel(job.location.name),
    }));
  }

  async fetch(url: string): Promise<DiscoveredListing> {
    // Greenhouse job URLs have the format: .../jobs/{id}
    // The JSON API endpoint appends ?questions=true for form fields
    const canonicalUrl = this.canonicalize(url);

    // Extract job ID from URL
    const jobIdMatch = canonicalUrl.match(/\/jobs\/(\d+)/);
    if (!jobIdMatch?.[1]) {
      throw new Error(`Cannot extract Greenhouse job ID from URL: ${url}`);
    }

    // Extract board slug from URL
    const boardMatch = canonicalUrl.match(/boards\.greenhouse\.io\/([^/]+)/);
    if (!boardMatch?.[1]) {
      throw new Error(`Cannot extract Greenhouse board slug from URL: ${url}`);
    }

    const apiUrl = `${BOARDS_API_BASE}/${boardMatch[1]}/jobs/${jobIdMatch[1]}`;
    const response = await fetch(apiUrl, {
      headers: { Accept: 'application/json' },
      signal: AbortSignal.timeout(15_000),
    });

    if (!response.ok) {
      throw new Error(`Greenhouse API returned HTTP ${response.status} for job ${jobIdMatch[1]}`);
    }

    const job = (await response.json()) as GreenhouseJob;

    return {
      canonicalUrl,
      companyName: boardMatch[1],
      roleTitle: job.title,
      location: job.location.name || undefined,
      remoteModel: inferRemoteModel(job.location.name),
      descriptionMarkdown: job.content ? stripHtml(job.content) : undefined,
      descriptionHtml: job.content ?? undefined,
    };
  }

  canonicalize(url: string): string {
    try {
      const parsed = new URL(url);
      // Normalize to boards.greenhouse.io if it's a different format
      // Strip query params and fragments
      return `${parsed.origin}${parsed.pathname}`.replace(/\/+$/, '');
    } catch {
      return url;
    }
  }
}
