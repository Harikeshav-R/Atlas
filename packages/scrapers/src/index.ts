import type { Listing } from '@atlas/schemas';

export interface ScraperAdapter {
  readonly platform: string;
  list(sourceConfig: unknown): Promise<readonly Listing[]>;
  fetch(url: string): Promise<Listing>;
}

export const scraperRegistry: Readonly<Record<string, ScraperAdapter>> = Object.freeze({});
