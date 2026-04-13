import type { AgentDefinition } from '@atlas/harness';
import { profileParserPrompt } from './prompt.ts';

export const profileParserAgent: AgentDefinition = {
  name: 'profile-parser',
  systemPrompt: profileParserPrompt,
  toolAllowlist: ['read', 'validate_schema'],
  stage: 'generation',
  budgets: {
    maxTokens: 8000,
    maxCostMilliUsd: 150,
    maxWallClockMs: 30000,
    maxToolCalls: 5,
  },
};
