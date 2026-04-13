import { sqliteTable, text, integer, index, real } from 'drizzle-orm/sqlite-core';
import { runs } from './runs.ts';
import { traceEvents } from './trace_events.ts';

export const costs = sqliteTable('costs', {
  cost_id: text('cost_id').primaryKey(),
  run_id: text('run_id').notNull().references(() => runs.run_id, { onDelete: 'cascade' }),
  event_id: text('event_id').notNull().references(() => traceEvents.event_id, { onDelete: 'cascade' }),
  model_id: text('model_id').notNull(),
  prompt_tokens: integer('prompt_tokens').notNull(),
  output_tokens: integer('output_tokens').notNull(),
  cost_usd: real('cost_usd').notNull(),
  timestamp: text('timestamp').notNull(),
}, (table) => ({
  runIdIdx: index('costs_run_id_idx').on(table.run_id),
  timestampIdx: index('costs_timestamp_idx').on(table.timestamp),
  modelIdIdx: index('costs_model_id_idx').on(table.model_id),
}));
