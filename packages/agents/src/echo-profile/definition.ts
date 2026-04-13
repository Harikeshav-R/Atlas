import type { AgentDefinition } from '@atlas/harness';
import { echoProfilePrompt } from './prompt.ts';

export const echoProfileAgent: AgentDefinition = {
  name: 'echo-profile',
  systemPrompt: echoProfilePrompt,
  toolAllowlist: ['get_profile'],
  stage: 'triage',
  budgets: {
    maxTokens: 1000,
    maxCostMilliUsd: 50,
    maxWallClockMs: 5000,
    maxToolCalls: 2,
  },
};
