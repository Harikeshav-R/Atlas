import { sqliteTable, text, integer } from 'drizzle-orm/sqlite-core';

export const profiles = sqliteTable('profiles', {
  profile_id: text('profile_id').primaryKey(),
  yaml_blob: text('yaml_blob').notNull(),
  parsed_json: text('parsed_json').notNull(),
  version: integer('version').notNull(),
  schema_version: integer('schema_version').notNull(),
  created_at: text('created_at').notNull(),
  updated_at: text('updated_at').notNull(),
});
