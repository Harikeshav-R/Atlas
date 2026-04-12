import { runAgent } from '@atlas/harness';
import { getAgent } from './registry.ts';

async function main() {
  const agentName = process.argv[2];
  if (!agentName) {
    console.error('Usage: pnpm run agent <agent-name>');
    process.exit(1);
  }

  const agent = getAgent(agentName);
  if (!agent) {
    console.error(`Agent not found: ${agentName}`);
    process.exit(1);
  }

  console.log(`Starting agent: ${agentName}`);

  // Fake options since we're in Phase 0
  const result = await runAgent(agent, {}, {
    fakes: {
      modelFn: async (iteration) => {
        if (iteration === 0) return { type: 'tool_call', toolName: 'get_profile', args: { profile_id: 'default' }, costMilliUsd: 0, tokens: 0 };
        return { type: 'text', text: 'CLI Test Echo', costMilliUsd: 0, tokens: 0 };
      },
      mcpCallFn: async () => ({})
    },
    onTraceEvent: (e) => console.log(`[trace] ${e.type} -`, JSON.stringify(e.payload))
  });

  if (result.ok) {
    console.log(`Finished: ${result.data.status}`);
    console.log(`Output: ${result.data.output}`);
  } else {
    console.error(`Error:`, result.error);
  }
}

main().catch(console.error);
