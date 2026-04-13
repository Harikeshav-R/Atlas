export type { ScraperAdapter, SourceConfig, DiscoveredListing } from './types.ts';
export { DiscoveredListingSchema } from './types.ts';
export { GreenhouseAdapter } from './greenhouse/index.ts';

import type { ScraperAdapter } from './types.ts';
import { GreenhouseAdapter } from './greenhouse/index.ts';

const greenhouse = new GreenhouseAdapter();

export const scraperRegistry: Readonly<Record<string, ScraperAdapter>> = Object.freeze({
  ats_greenhouse: greenhouse,
});
