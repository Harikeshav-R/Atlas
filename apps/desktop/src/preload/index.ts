import { contextBridge, ipcRenderer } from 'electron';
import { IpcChannels, type IpcChannel } from '@atlas/schemas';

const validChannels = new Set<string>(Object.values(IpcChannels));

const api = {
  invoke: <T = unknown>(channel: IpcChannel, payload?: unknown): Promise<T> => {
    if (!validChannels.has(channel)) throw new Error(`Invalid channel: ${channel}`);
    return ipcRenderer.invoke(channel, payload);
  },
  on: (channel: IpcChannel, handler: (payload: unknown) => void) => {
    if (!validChannels.has(channel)) throw new Error(`Invalid channel: ${channel}`);
    const listener = (_: unknown, payload: unknown) => handler(payload);
    ipcRenderer.on(channel, listener);
    return () => ipcRenderer.removeListener(channel, listener);
  },
};

contextBridge.exposeInMainWorld('atlas', api);
