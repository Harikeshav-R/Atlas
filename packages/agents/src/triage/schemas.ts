import { z } from 'zod';

export const TriageInputSchema = z.object({
  listingId: z.string().min(1),
});

export type TriageInput = z.infer<typeof TriageInputSchema>;

export const TriageOutputSchema = z.object({
  score: z.number().min(0).max(10),
  go: z.boolean(),
  reason: z.string().min(1),
});

export type TriageOutput = z.infer<typeof TriageOutputSchema>;
