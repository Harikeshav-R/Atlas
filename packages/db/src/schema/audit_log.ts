import { sqliteTable, text } from 'drizzle-orm/sqlite-core';

export const auditLog = sqliteTable('audit_log', {
  log_id: text('log_id').primaryKey(),
  timestamp: text('timestamp').notNull(),
  actor: text('actor').notNull(),
  action: text('action').notNull(),
  target_kind: text('target_kind'),
  target_id: text('target_id'),
  details_json: text('details_json'),
});
