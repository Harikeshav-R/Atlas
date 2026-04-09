import { app, BrowserWindow, session } from 'electron';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';
import { createLogger } from '@atlas/shared';

const log = createLogger('main');
const here = dirname(fileURLToPath(import.meta.url));

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

  win.webContents.on('did-fail-load', (_e, code, desc, url) => {
    log.error({ code, desc, url }, 'renderer failed to load');
  });
  win.webContents.on('render-process-gone', (_e, details) => {
    log.error({ details }, 'renderer process gone');
  });

  try {
    if (isDev) {
      log.info({ url: process.env.ELECTRON_RENDERER_URL }, 'loading dev renderer');
      await win.loadURL(process.env.ELECTRON_RENDERER_URL!);
      win.webContents.openDevTools({ mode: 'detach' });
    } else {
      await win.loadFile(resolve(here, '../renderer/index.html'));
    }
  } catch (err) {
    log.error({ err }, 'loadURL/loadFile threw');
  }

  return win;
}

app.whenReady().then(async () => {
  log.info('atlas desktop starting');
  await createMainWindow();
  app.on('activate', async () => {
    if (BrowserWindow.getAllWindows().length === 0) await createMainWindow();
  });
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit();
});

app.on('web-contents-created', (_e, contents) => {
  contents.setWindowOpenHandler(() => ({ action: 'deny' }));
  contents.on('will-navigate', (e) => e.preventDefault());
});
