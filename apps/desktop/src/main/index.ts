import { app, BrowserWindow, session, ipcMain } from 'electron';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';
import { createHash } from 'node:crypto';
import { createLogger, ok, err, newId, nowISO } from '@atlas/shared';
import { createDb, queries, profiles, listings } from '@atlas/db';
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
          const runId = (e.payload as { runId?: string })?.runId;
          if (!runId) {
            log.error({ event: e }, 'run_started event missing runId; skipping run insert');
            return;
          }
          queries.insertRun(db, {
            run_id: runId,
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
      db.delete(profiles).where(eq(profiles.profile_id, 'default')).run();
      
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
            run_id: payload?.runId || newId('run'),
            agent_name: agentName,
            mode: 'normal',
            started_at: nowISO(),
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

// Listings handlers
ipcMain.handle('listings.list', () => {
  try {
    const result = queries.listListings(db, { limit: 50 });
    return ok(result);
  } catch (e: unknown) {
    const message = e instanceof Error ? e.message : String(e);
    return err({ name: 'AtlasError', code: 'INTERNAL', message });
  }
});

ipcMain.handle('listings.get', (_event, listingId: string) => {
  try {
    const listing = queries.getListing(db, listingId);
    if (!listing) return err({ name: 'AtlasError', code: 'NOT_FOUND', message: 'Listing not found' });

    const evaluation = queries.getEvaluationForListing(db, listingId);
    const scorecard = evaluation ? queries.getScorecard(db, evaluation.evaluation_id) : undefined;

    return ok({ listing, evaluation, scorecard });
  } catch (e: unknown) {
    const message = e instanceof Error ? e.message : String(e);
    return err({ name: 'AtlasError', code: 'INTERNAL', message });
  }
});

ipcMain.handle('listings.createFromUrl', async (_event, url: string) => {
  try {
    // Canonicalize the URL
    const parsed = new URL(url);
    const canonicalUrl = `${parsed.origin}${parsed.pathname}`.replace(/\/+$/, '');

    // Check for existing listing with this URL
    const existing = queries.getListingByUrl(db, canonicalUrl);
    if (existing) {
      return ok(existing);
    }

    // Fetch the page content to extract job info
    // For Phase 1 MVP, we create a stub listing with the URL;
    // the evaluation agent will read the full details via web tools
    const timestamp = nowISO();
    const listingId = newId('listing');

    queries.insertListing(db, {
      listing_id: listingId,
      canonical_url: canonicalUrl,
      company_name: parsed.hostname.replace(/^(www\.|boards\.)/, '').split('.')[0] ?? 'Unknown',
      role_title: 'Pending evaluation...',
      first_seen_at: timestamp,
      last_seen_at: timestamp,
      status: 'active',
    });

    return ok(queries.getListing(db, listingId));
  } catch (e: unknown) {
    const message = e instanceof Error ? e.message : String(e);
    return err({ name: 'AtlasError', code: 'INTERNAL', message });
  }
});

ipcMain.handle('listings.evaluate', async (_event, listingId: string) => {
  try {
    const listing = queries.getListing(db, listingId);
    if (!listing) return err({ name: 'AtlasError', code: 'NOT_FOUND', message: 'Listing not found' });

    // For Phase 1 MVP, run with fakes — real model integration comes when
    // the model router is wired up to actual providers via Settings
    const agent = getAgent('evaluation.deep');
    if (!agent) return err({ name: 'AtlasError', code: 'INTERNAL', message: 'Evaluation agent not found' });

    const runId = newId('run');
    const timestamp = nowISO();

    queries.insertRun(db, {
      run_id: runId,
      agent_name: 'evaluation.deep',
      mode: 'normal',
      started_at: timestamp,
      status: 'running',
    });

    // Placeholder evaluation result — in production this comes from the agent
    // For now we create a stub evaluation so the UI can render
    const evaluationId = newId('eval');
    const profileRow = queries.getProfile(db, 'default');
    const profileVersion = profileRow?.version ?? 1;

    const stubSixBlocks = {
      roleSummary: { dayToDay: ['Evaluation pending — run with a configured API key to get real results'] },
      cvMatch: { matches: [{ requirement: 'Pending', gap: false }], gapsSummary: 'Pending evaluation' },
      levelStrategy: { targetSeniority: 'Pending', emphasize: [], deemphasize: [] },
      compResearch: { leveragePoints: [], sources: [] },
      personalization: { companyNews: [], productLaunches: [], engineeringBlog: [], coverLetterHooks: [] },
      interviewPrep: { stages: [], gaps: [] },
    };

    queries.insertEvaluation(db, {
      evaluation_id: evaluationId,
      listing_id: listingId,
      profile_version: profileVersion,
      agent_run_id: runId,
      grade: 'C',
      score: 5.5,
      six_blocks_json: JSON.stringify(stubSixBlocks),
      summary_text: 'Stub evaluation — configure an API key in Settings to run real evaluations.',
      created_at: timestamp,
    });

    queries.updateRunStatus(db, runId, 'succeeded', nowISO());

    const evaluation = queries.getEvaluation(db, evaluationId);
    return ok(evaluation);
  } catch (e: unknown) {
    const message = e instanceof Error ? e.message : String(e);
    return err({ name: 'AtlasError', code: 'INTERNAL', message });
  }
});

// Settings handlers
// For Phase 1 MVP, settings are stored in the preferences table.
// API keys would use keytar in production; for now we use the preferences table.
ipcMain.handle('settings.get', () => {
  try {
    const prefs = queries.getPreferences(db, 'default');
    return ok(prefs ?? {
      model_routing_json: JSON.stringify({
        triage: 'anthropic/claude-haiku-4-5',
        evaluation: 'anthropic/claude-sonnet-4-5',
        generation: 'anthropic/claude-sonnet-4-5',
        verification: 'anthropic/claude-sonnet-4-5',
        navigation: 'anthropic/claude-sonnet-4-5',
        interaction: 'anthropic/claude-sonnet-4-5',
      }),
      budgets_json: JSON.stringify({ monthlyBudgetUsd: 50 }),
    });
  } catch (e: unknown) {
    const message = e instanceof Error ? e.message : String(e);
    return err({ name: 'AtlasError', code: 'INTERNAL', message });
  }
});

ipcMain.handle('settings.save', (_event, settings: Record<string, unknown>) => {
  try {
    queries.upsertPreferences(db, {
      preferences_id: 'default_prefs',
      profile_id: 'default',
      model_routing_json: settings.modelRouting ? JSON.stringify(settings.modelRouting) : undefined,
      budgets_json: settings.budgets ? JSON.stringify(settings.budgets) : undefined,
      scoring_weights_json: settings.scoringWeights ? JSON.stringify(settings.scoringWeights) : undefined,
      grade_thresholds_json: settings.gradeThresholds ? JSON.stringify(settings.gradeThresholds) : undefined,
      updated_at: nowISO(),
    });
    return ok(true);
  } catch (e: unknown) {
    const message = e instanceof Error ? e.message : String(e);
    return err({ name: 'AtlasError', code: 'INTERNAL', message });
  }
});

ipcMain.handle('settings.setApiKey', (_event, provider: string, _apiKey: string) => {
  // In production: keytar.setPassword('atlas', `llm-provider/${provider}`, apiKey)
  // For Phase 1 MVP, we store a flag indicating the key is set
  log.info({ provider }, 'API key set (stub — keytar not wired yet)');
  return ok(true);
});

ipcMain.handle('settings.deleteApiKey', (_event, provider: string) => {
  log.info({ provider }, 'API key deleted (stub)');
  return ok(true);
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

  win.webContents.setWindowOpenHandler(() => {
    return { action: 'deny' };
  });

  win.webContents.on('will-navigate', (e, url) => {
    if (isDev && url.startsWith(process.env.ELECTRON_RENDERER_URL!)) return;
    if (!isDev && url.startsWith('file://')) return;
    e.preventDefault();
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
