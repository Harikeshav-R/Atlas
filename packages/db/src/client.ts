import Database from 'better-sqlite3';
import { drizzle, type BetterSQLite3Database } from 'drizzle-orm/better-sqlite3';
import { migrate } from 'drizzle-orm/better-sqlite3/migrator';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';
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

export function createDb(path: string): AtlasDb {
  const db = openDb({ path });
  const here = dirname(fileURLToPath(import.meta.url));
  const migrationsFolder = resolve(here, '../migrations');
  migrate(db, { migrationsFolder });
  return db;
}
