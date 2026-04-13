import { sqliteTable, text } from 'drizzle-orm/sqlite-core';
import { profiles } from './profiles.ts';

export const preferences = sqliteTable('preferences', {
  preferences_id: text('preferences_id').primaryKey(),
  profile_id: text('profile_id').notNull().references(() => profiles.profile_id, { onDelete: 'cascade' }),
  scoring_weights_json: text('scoring_weights_json'),
  grade_thresholds_json: text('grade_thresholds_json'),
  model_routing_json: text('model_routing_json'),
  budgets_json: text('budgets_json'),
  notification_prefs_json: text('notification_prefs_json'),
  updated_at: text('updated_at').notNull(),
});
