import type { AgentDefinition } from '@atlas/harness';
import { echoProfileAgent } from './echo-profile/definition.ts';
import { profileParserAgent } from './profile-parser/definition.ts';
import { triageAgent } from './triage/definition.ts';

/**
 * Registry of all primary agents.
 */
export const agentRegistry: Readonly<Record<string, AgentDefinition>> = Object.freeze({
  'echo-profile': echoProfileAgent,
  'profile-parser': profileParserAgent,
  'triage': triageAgent,
});

export function getAgent(name: string): AgentDefinition | undefined {
  return agentRegistry[name];
}
