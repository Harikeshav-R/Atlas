import { app, BrowserWindow, session, ipcMain } from 'electron';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';
import { createLogger, ok, err } from '@atlas/shared';
import { createDb, queries, profiles } from '@atlas/db';
import { runAgent } from '@atlas/harness';
import { getAgent } from '@atlas/agents';
import { eq } from 'drizzle-orm';

const log = createLogger('main');
const here = dirname(fileURLToPath(import.meta.url));

// Phase 0 DB setup
const dbPath = resolve(app.getPath('userData'), 'atlas.sqlite');

// Resolve migrations path
let migrationsPath: string;
if (app.isPackaged) {
  migrationsPath = resolve(process.resourcesPath, 'migrations');
} else {
  // In dev, we can point directly to the source package
  migrationsPath = resolve(here, '../../../../packages/db/migrations');
}

const db = createDb(dbPath, migrationsPath);

// Seed fake profile
try {
  if (!queries.getProfile(db, 'default')) {
    queries.insertProfile(db, {
      profile_id: 'default',
      yaml_blob: 'name: Atlas User',
      parsed_json: '{"name":"Atlas User"}',
      version: 1,
      schema_version: 1,
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    });
  }
} catch (e) {
  log.error({ err: e }, 'Failed to seed profile');
}

// IPC handlers
ipcMain.handle('profile.get', () => {
  try {
    return ok(queries.getProfile(db, 'default'));
  } catch (e: unknown) {
    const message = e instanceof Error ? e.message : String(e);
    return err({ name: 'AtlasError', code: 'INTERNAL', message });
  }
});

ipcMain.handle('profile.import', async (_event, filePath: string) => {
  try {
    const agent = getAgent('profile-parser');
    if (!agent) throw new Error('profile-parser agent not found');

    const res = await runAgent(agent, { file_path: filePath }, {
      fakes: {
        modelFn: async (iteration) => {
          if (iteration === 0) return { type: 'tool_call', toolName: 'read', args: { path: filePath }, costMilliUsd: 10, tokens: 500 };
          if (iteration === 1) return { type: 'tool_call', toolName: 'validate_schema', args: { yaml_string: 'version: 1\\nname: "Imported User"' }, costMilliUsd: 5, tokens: 100 };
          return { type: 'text', text: 'version: 1\\nname: "Imported User"\\ncontact:\\n  email: "test@example.com"', costMilliUsd: 5, tokens: 100 };
        },
        mcpCallFn: async () => ({})
      },
      onTraceEvent: (e) => {
        if (e.type === 'run_started') {
          const payload = e.payload as { runId?: string } | undefined;
          queries.insertRun(db, {
            run_id: payload?.runId || `run_${Date.now()}`,
            agent_name: 'profile-parser',
            mode: 'normal',
            started_at: new Date().toISOString(),
            status: 'running'
          });
        }
      }
    });

    if (res.ok) {
      const existing = queries.getProfile(db, 'default');
      const version = existing ? existing.version + 1 : 1;
      
      // Update the canonical profile in DB
      try {
        db.delete(profiles).where(eq(profiles.profile_id, 'default')).run();
      } catch {}
      
      queries.insertProfile(db, {
        profile_id: 'default',
        yaml_blob: res.data.output as string,
        parsed_json: JSON.stringify({ name: 'Imported User' }),
        version,
        schema_version: 1,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString()
      });
    }

    return res;
  } catch (e: unknown) {
    const message = e instanceof Error ? e.message : String(e);
    return err({ name: 'AtlasError', code: 'INTERNAL', message });
  }
});

ipcMain.handle('runs.start', async (_event, agentName: string) => {
  try {
    const agent = getAgent(agentName);
    if (!agent) throw new Error('Agent not found');

    const res = await runAgent(agent, { profile_id: 'default' }, {
      fakes: {
        modelFn: async (iteration) => {
          if (iteration === 0) return { type: 'tool_call', toolName: 'get_profile', args: { profile_id: 'default' }, costMilliUsd: 10, tokens: 100 };
          return { type: 'text', text: 'Atlas User', costMilliUsd: 5, tokens: 50 };
        },
        mcpCallFn: async () => ({ name: 'Atlas User' })
      },
      onTraceEvent: (e) => {
        // In real impl, we insert trace event into DB here
        log.info({ type: e.type }, 'Trace event');
        if (e.type === 'run_started') {
          // ensure run row exists
          const payload = e.payload as { runId?: string } | undefined;
          queries.insertRun(db, {
            run_id: payload?.runId || `run_${Date.now()}`,
            agent_name: agentName,
            mode: 'normal',
            started_at: new Date().toISOString(),
            status: 'running'
          });
        }
      }
    });

    return res;
  } catch (e: unknown) {
    const message = e instanceof Error ? e.message : String(e);
    return err({ name: 'AtlasError', code: 'INTERNAL', message });
  }
});

ipcMain.handle('runs.get', (_event, runId: string) => {
  // Stub for now, normally we fetch traces from db
  return ok({ runId, traces: [] });
});

async function createMainWindow(): Promise<BrowserWindow> {
  const win = new BrowserWindow({
    width: 1400,
    height: 900,
    show: true,
    webPreferences: {
      preload: resolve(here, '../preload/index.js'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
      webSecurity: true,
    },
  });

  const isDev = !!process.env.ELECTRON_RENDERER_URL;
  const csp = isDev
    ? "default-src 'self' 'unsafe-inline' 'unsafe-eval' data: blob: ws: http://localhost:* http://127.0.0.1:*; img-src 'self' data: blob:; connect-src 'self' ws: http://localhost:* http://127.0.0.1:*"
    : "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'";

  session.defaultSession.webRequest.onHeadersReceived((details, cb) => {
    cb({
      responseHeaders: {
        ...details.responseHeaders,
        'Content-Security-Policy': [csp],
      },
    });
  });

  if (isDev) {
    await win.loadURL(process.env.ELECTRON_RENDERER_URL!);
    win.webContents.openDevTools({ mode: 'detach' });
  } else {
    await win.loadFile(resolve(here, '../renderer/index.html'));
  }

  return win;
}

app.whenReady().then(async () => {
  await createMainWindow();
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit();
});
