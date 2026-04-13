import { z } from 'zod';

export const echoProfileInputSchema = z.object({
  profile_id: z.string(),
});

export const echoProfileOutputSchema = z.string();
