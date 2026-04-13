import type { AgentDefinition } from '@atlas/harness';
import { triagePrompt } from './prompt.ts';

export const triageAgent: AgentDefinition = {
  name: 'triage',
  systemPrompt: triagePrompt,
  toolAllowlist: [
    'atlas-db.get_profile',
    'atlas-db.read_listing',
  ],
  stage: 'triage',
  budgets: {
    maxTokens: 4_000,
    maxCostMilliUsd: 20, // ~$0.02 — this should be very cheap
    maxWallClockMs: 30_000,
    maxToolCalls: 4,
  },
};
