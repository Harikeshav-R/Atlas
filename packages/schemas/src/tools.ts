import { z } from 'zod';

/** Base schema for all MCP tool results. */
export const ToolResultSchema = z.discriminatedUnion('ok', [
  z.object({
    ok: z.literal(true),
    data: z.unknown(),
  }),
  z.object({
    ok: z.literal(false),
    error: z.object({
      code: z.string(),
      message: z.string(),
      details: z.record(z.string(), z.unknown()).optional(),
    }),
  }),
]);

export type ToolResult = z.infer<typeof ToolResultSchema>;

/** Common arguments for pagination. */
export const PaginationArgsSchema = z.object({
  limit: z.number().int().min(1).max(100).default(20),
  offset: z.number().int().min(0).default(0),
});

/** Common ID arg. */
export const IdArgSchema = z.object({
  id: z.string(),
});
