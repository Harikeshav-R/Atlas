import Database from 'better-sqlite3';
import { drizzle, type BetterSQLite3Database } from 'drizzle-orm/better-sqlite3';
import * as schema from './schema/index.ts';

export type AtlasDb = BetterSQLite3Database<typeof schema>;

export interface OpenDbOptions {
  readonly path: string;
  readonly readonly?: boolean;
}

export function openDb(opts: OpenDbOptions): AtlasDb {
  const sqlite = new Database(opts.path, { readonly: opts.readonly ?? false });
  sqlite.pragma('journal_mode = WAL');
  sqlite.pragma('foreign_keys = ON');
  return drizzle(sqlite, { schema });
}
