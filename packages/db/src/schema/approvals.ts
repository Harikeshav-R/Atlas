import { sqliteTable, text, integer } from 'drizzle-orm/sqlite-core';

export const approvals = sqliteTable('approvals', {
  id: text('id').primaryKey(),
  runId: text('run_id').notNull(),
  scope: text('scope').notNull(),
  question: text('question').notNull(),
  status: text('status').notNull(), // pending | granted | denied | expired
  requestedAt: integer('requested_at', { mode: 'timestamp_ms' }).notNull(),
  respondedAt: integer('responded_at', { mode: 'timestamp_ms' }),
  responseNote: text('response_note'),
});
