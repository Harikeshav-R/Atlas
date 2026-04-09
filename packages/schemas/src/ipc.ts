import { z } from 'zod';

/** IPC channel registry — all renderer<->main traffic is declared here. */
export const IpcChannels = {
  profileImport: 'profile.import',
  profileGet: 'profile.get',
  runsStart: 'runs.start',
  runsKill: 'runs.kill',
  runsList: 'runs.list',
  approvalsRespond: 'approvals.respond',
  listingsList: 'listings.list',
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
