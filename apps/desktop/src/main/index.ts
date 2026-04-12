import { app, BrowserWindow, session, ipcMain } from 'electron';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';
import { createLogger, ok, err } from '@atlas/shared';
import { createDb, queries } from '@atlas/db';
import { runAgent } from '@atlas/harness';
import { getAgent } from '@atlas/agents';

const log = createLogger('main');
const here = dirname(fileURLToPath(import.meta.url));

// Phase 0 DB setup
const dbPath = resolve(app.getPath('userData'), 'atlas.sqlite');
const db = createDb(dbPath);

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
  } catch (e: any) {
    return err({ name: 'AtlasError', code: 'INTERNAL', message: e.message });
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
          queries.insertRun(db, {
            run_id: (e.payload as any)?.runId || `run_${Date.now()}`,
            agent_name: agentName,
            mode: 'normal',
            started_at: new Date().toISOString(),
            status: 'running'
          });
        }
      }
    });

    return res;
  } catch (e: any) {
    return err({ name: 'AtlasError', code: 'INTERNAL', message: e.message });
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
