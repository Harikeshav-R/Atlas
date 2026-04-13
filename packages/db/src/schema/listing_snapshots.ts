import { sqliteTable, text, index } from 'drizzle-orm/sqlite-core';
import { listings } from './listings.ts';

export const listingSnapshots = sqliteTable('listing_snapshots', {
  snapshot_id: text('snapshot_id').primaryKey(),
  listing_id: text('listing_id').notNull().references(() => listings.listing_id, { onDelete: 'cascade' }),
  captured_at: text('captured_at').notNull(),
  raw_html_path: text('raw_html_path'),
  extracted_text: text('extracted_text'),
  content_hash: text('content_hash'),
}, (table) => ({
  listingIdIdx: index('listing_snapshots_listing_id_idx').on(table.listing_id),
}));
