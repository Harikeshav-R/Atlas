import { sqliteTable, text, integer } from 'drizzle-orm/sqlite-core';

export const runs = sqliteTable('runs', {
  id: text('id').primaryKey(),
  agent: text('agent').notNull(),
  status: text('status').notNull(), // queued | running | finished | failed | killed
  startedAt: integer('started_at', { mode: 'timestamp_ms' }).notNull(),
  finishedAt: integer('finished_at', { mode: 'timestamp_ms' }),
  costUsd: integer('cost_usd_milli').notNull().default(0), // stored as milli-USD
  tokensIn: integer('tokens_in').notNull().default(0),
  tokensOut: integer('tokens_out').notNull().default(0),
  error: text('error'),
});

export const traceEvents = sqliteTable('trace_events', {
  id: text('id').primaryKey(),
  runId: text('run_id')
    .notNull()
    .references(() => runs.id, { onDelete: 'cascade' }),
  ts: integer('ts', { mode: 'timestamp_ms' }).notNull(),
  type: text('type').notNull(),
  agent: text('agent'),
  payload: text('payload', { mode: 'json' }).notNull(),
});
