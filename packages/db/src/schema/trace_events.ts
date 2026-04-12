import { sqliteTable, text, integer, index, real } from 'drizzle-orm/sqlite-core';
import { runs } from './runs.ts';

export const traceEvents = sqliteTable('trace_events', {
  event_id: text('event_id').primaryKey(),
  run_id: text('run_id').notNull().references(() => runs.run_id, { onDelete: 'cascade' }),
  parent_event_id: text('parent_event_id').references((): any => traceEvents.event_id, { onDelete: 'cascade' }),
  step_index: integer('step_index').notNull(),
  timestamp: text('timestamp').notNull(),
  type: text('type').notNull(),
  actor: text('actor'),
  payload_json: text('payload_json'),
  cost_usd: real('cost_usd'),
  duration_ms: integer('duration_ms'),
}, (table) => ({
  runIdIdx: index('trace_events_run_id_idx').on(table.run_id),
  runStepIdx: index('trace_events_run_id_step_index_idx').on(table.run_id, table.step_index),
  typeIdx: index('trace_events_type_idx').on(table.type),
}));
