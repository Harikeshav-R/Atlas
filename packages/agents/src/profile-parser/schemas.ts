import { z } from 'zod';

export const profileParserInputSchema = z.object({
  file_path: z.string()
});

export const profileParserOutputSchema = z.string();
