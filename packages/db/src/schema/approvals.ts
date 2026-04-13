import { sqliteTable, text, index } from 'drizzle-orm/sqlite-core';
import { runs } from './runs.ts';

export const approvals = sqliteTable('approvals', {
  approval_id: text('approval_id').primaryKey(),
  run_id: text('run_id').notNull().references(() => runs.run_id, { onDelete: 'cascade' }),
  scope: text('scope').notNull(),
  title: text('title').notNull(),
  description: text('description').notNull(),
  screenshot_path: text('screenshot_path'),
  options_json: text('options_json').notNull(),
  status: text('status').notNull(), // pending | granted | denied | timed_out
  user_response_json: text('user_response_json'),
  requested_at: text('requested_at').notNull(),
  responded_at: text('responded_at'),
  timeout_at: text('timeout_at').notNull(),
}, (table) => ({
  statusIdx: index('approvals_status_idx').on(table.status),
  runIdIdx: index('approvals_run_id_idx').on(table.run_id),
}));
