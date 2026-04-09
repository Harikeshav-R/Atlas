import { z } from 'zod';

export const ListingSchema = z.object({
  id: z.string(),
  sourceId: z.string(),
  url: z.url(),
  title: z.string(),
  company: z.string(),
  location: z.string().optional(),
  remote: z.enum(['remote', 'hybrid', 'onsite', 'unknown']).default('unknown'),
  descriptionMarkdown: z.string(),
  postedAt: z.string().datetime().optional(),
  discoveredAt: z.string().datetime(),
  fingerprint: z.string(),
});

export type Listing = z.infer<typeof ListingSchema>;
