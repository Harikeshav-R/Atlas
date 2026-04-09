import type { AgentDefinition } from '@atlas/harness';

/**
 * Registry of all primary agents. Stub — individual agent definitions will
 * live under `src/{agent-name}/definition.ts` and be imported here.
 * See technical-design.md Appendix A.
 */
export const agentRegistry: Readonly<Record<string, AgentDefinition>> = Object.freeze({});

export function getAgent(name: string): AgentDefinition | undefined {
  return agentRegistry[name];
}
