import { sqliteTable, text, integer, index, uniqueIndex } from 'drizzle-orm/sqlite-core';

export const listings = sqliteTable('listings', {
  listing_id: text('listing_id').primaryKey(),
  canonical_url: text('canonical_url').notNull(),
  company_name: text('company_name').notNull(),
  role_title: text('role_title').notNull(),
  location: text('location'),
  remote_model: text('remote_model').notNull().default('unknown'), // remote | hybrid | onsite | unknown
  description_markdown: text('description_markdown'),
  description_hash: text('description_hash'),
  first_seen_at: text('first_seen_at').notNull(),
  last_seen_at: text('last_seen_at').notNull(),
  removed_at: text('removed_at'),
  status: text('status').notNull().default('active'), // active | removed
}, (table) => ({
  canonicalUrlIdx: uniqueIndex('listings_canonical_url_idx').on(table.canonical_url),
  companyNameIdx: index('listings_company_name_idx').on(table.company_name),
  firstSeenAtIdx: index('listings_first_seen_at_idx').on(table.first_seen_at),
  statusIdx: index('listings_status_idx').on(table.status),
}));
