import type { AgentDefinition } from '@atlas/harness';
import { echoProfileAgent } from './echo-profile/definition.ts';

/**
 * Registry of all primary agents.
 */
export const agentRegistry: Readonly<Record<string, AgentDefinition>> = Object.freeze({
  'echo-profile': echoProfileAgent,
});

export function getAgent(name: string): AgentDefinition | undefined {
  return agentRegistry[name];
}
