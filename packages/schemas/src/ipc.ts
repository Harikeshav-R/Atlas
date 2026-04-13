import { z } from 'zod';

/** IPC channel registry — all renderer<->main traffic is declared here. */
export const IpcChannels = {
  profileImport: 'profile.import',
  profileGet: 'profile.get',
  runsStart: 'runs.start',
  runsGet: 'runs.get',
  runsKill: 'runs.kill',
  runsList: 'runs.list',
  approvalsRespond: 'approvals.respond',
  listingsList: 'listings.list',
  listingsGet: 'listings.get',
  listingsCreateFromUrl: 'listings.createFromUrl',
  listingsEvaluate: 'listings.evaluate',
  settingsGet: 'settings.get',
  settingsSave: 'settings.save',
  settingsSetApiKey: 'settings.setApiKey',
  settingsDeleteApiKey: 'settings.deleteApiKey',
} as const;

export type IpcChannel = (typeof IpcChannels)[keyof typeof IpcChannels];

export const IpcErrorSchema = z.object({
  code: z.string(),
  message: z.string(),
  details: z.record(z.string(), z.unknown()).optional(),
});

export const IpcResultSchema = <T extends z.ZodTypeAny>(data: T) =>
  z.discriminatedUnion('ok', [
    z.object({ ok: z.literal(true), data }),
    z.object({ ok: z.literal(false), error: IpcErrorSchema }),
  ]);

export type IpcResult<T> =
  | { ok: true; data: T }
  | { ok: false; error: z.infer<typeof IpcErrorSchema> };
