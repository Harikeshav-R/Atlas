import { z } from 'zod';

/** Shape returned by scraper adapters before DB persistence. */
export const DiscoveredListingSchema = z.object({
  canonicalUrl: z.string().url(),
  companyName: z.string().min(1),
  roleTitle: z.string().min(1),
  location: z.string().optional(),
  remoteModel: z.enum(['remote', 'hybrid', 'onsite', 'unknown']).default('unknown'),
  descriptionMarkdown: z.string().optional(),
  descriptionHtml: z.string().optional(),
});

export type DiscoveredListing = z.infer<typeof DiscoveredListingSchema>;

export interface SourceConfig {
  readonly companySlug: string;
}

export interface ScraperAdapter {
  readonly platform: string;
  list(config: SourceConfig): Promise<readonly DiscoveredListing[]>;
  fetch(url: string): Promise<DiscoveredListing>;
  canonicalize(url: string): string;
}
