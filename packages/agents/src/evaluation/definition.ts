import type { AgentDefinition } from '@atlas/harness';
import { evaluationPrompt } from './prompt.ts';

export const evaluationAgent: AgentDefinition = {
  name: 'evaluation.deep',
  systemPrompt: evaluationPrompt,
  toolAllowlist: [
    'atlas-db.get_profile',
    'atlas-db.read_listing',
    'atlas-web.search',
    'atlas-web.fetch',
  ],
  stage: 'evaluation',
  budgets: {
    maxTokens: 32_000,
    maxCostMilliUsd: 500, // $0.50 — full eval budget
    maxWallClockMs: 120_000, // 2 minutes
    maxToolCalls: 20,
  },
};
