import { sqliteTable, text, integer, real, uniqueIndex } from 'drizzle-orm/sqlite-core';
import { listings } from './listings.ts';
import { runs } from './runs.ts';

export const evaluations = sqliteTable('evaluations', {
  evaluation_id: text('evaluation_id').primaryKey(),
  listing_id: text('listing_id').notNull().references(() => listings.listing_id, { onDelete: 'cascade' }),
  profile_version: integer('profile_version').notNull(),
  agent_run_id: text('agent_run_id').references(() => runs.run_id, { onDelete: 'set null' }),
  grade: text('grade').notNull(), // A | B | C | D | F
  score: real('score').notNull(), // 0-10
  six_blocks_json: text('six_blocks_json').notNull(),
  summary_text: text('summary_text').notNull(),
  created_at: text('created_at').notNull(),
}, (table) => ({
  listingProfileIdx: uniqueIndex('evaluations_listing_profile_idx').on(table.listing_id, table.profile_version),
}));
