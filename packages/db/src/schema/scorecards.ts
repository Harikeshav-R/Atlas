import { sqliteTable, text, real, uniqueIndex } from 'drizzle-orm/sqlite-core';
import { evaluations } from './evaluations.ts';

export const scorecards = sqliteTable('scorecards', {
  scorecard_id: text('scorecard_id').primaryKey(),
  evaluation_id: text('evaluation_id').notNull().references(() => evaluations.evaluation_id, { onDelete: 'cascade' }),
  dimensions_json: text('dimensions_json').notNull(), // array of 10 dimension objects
  weighted_total: real('weighted_total').notNull(),
}, (table) => ({
  evaluationIdIdx: uniqueIndex('scorecards_evaluation_id_idx').on(table.evaluation_id),
}));
