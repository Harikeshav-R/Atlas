import { contextBridge, ipcRenderer } from 'electron';

const api = {
  invoke: <T = unknown>(channel: string, payload?: unknown): Promise<T> =>
    ipcRenderer.invoke(channel, payload),
  on: (channel: string, handler: (payload: unknown) => void) => {
    const listener = (_: unknown, payload: unknown) => handler(payload);
    ipcRenderer.on(channel, listener);
    return () => ipcRenderer.removeListener(channel, listener);
  },
};

contextBridge.exposeInMainWorld('atlas', api);
