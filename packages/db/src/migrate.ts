import Database from 'better-sqlite3';
import { drizzle } from 'drizzle-orm/better-sqlite3';
import { migrate } from 'drizzle-orm/better-sqlite3/migrator';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';

const here = dirname(fileURLToPath(import.meta.url));
const dbPath = process.env.ATLAS_DB_PATH ?? resolve(here, '../atlas.dev.sqlite');
const sqlite = new Database(dbPath);
const db = drizzle(sqlite);
migrate(db, { migrationsFolder: resolve(here, '../migrations') });
sqlite.close();
console.log('[db] migrations applied at', dbPath);
