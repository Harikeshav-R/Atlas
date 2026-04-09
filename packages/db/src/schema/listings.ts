import { sqliteTable, text, integer } from 'drizzle-orm/sqlite-core';

export const listings = sqliteTable('listings', {
  id: text('id').primaryKey(),
  sourceId: text('source_id').notNull(),
  url: text('url').notNull(),
  title: text('title').notNull(),
  company: text('company').notNull(),
  location: text('location'),
  remote: text('remote').notNull().default('unknown'),
  descriptionMarkdown: text('description_markdown').notNull(),
  postedAt: integer('posted_at', { mode: 'timestamp_ms' }),
  discoveredAt: integer('discovered_at', { mode: 'timestamp_ms' }).notNull(),
  fingerprint: text('fingerprint').notNull().unique(),
});
