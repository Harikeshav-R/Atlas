import { z } from 'zod';

export const TraceEventTypeSchema = z.enum([
  'run_started',
  'run_finished',
  'model_call_started',
  'model_call_finished',
  'tool_call_started',
  'tool_call_finished',
  'approval_requested',
  'approval_granted',
  'approval_denied',
  'budget_exceeded',
  'error',
]);
export type TraceEventType = z.infer<typeof TraceEventTypeSchema>;

export const TraceEventSchema = z.object({
  id: z.string(),
  runId: z.string(),
  ts: z.string().datetime(),
  type: TraceEventTypeSchema,
  agent: z.string().optional(),
  payload: z.record(z.string(), z.unknown()).default({}),
});
export type TraceEvent = z.infer<typeof TraceEventSchema>;
