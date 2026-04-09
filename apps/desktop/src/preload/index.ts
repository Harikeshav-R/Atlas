import { contextBridge, ipcRenderer } from 'electron';
import { IpcChannels, type IpcChannel } from '@atlas/schemas';

const api = {
  invoke: <T = unknown>(channel: IpcChannel, payload?: unknown): Promise<T> =>
    ipcRenderer.invoke(channel, payload),
  on: (channel: IpcChannel, handler: (payload: unknown) => void) => {
    const listener = (_: unknown, payload: unknown) => handler(payload);
    ipcRenderer.on(channel, listener);
    return () => ipcRenderer.removeListener(channel, listener);
  },
  channels: IpcChannels,
};

contextBridge.exposeInMainWorld('atlas', api);

export type AtlasApi = typeof api;
