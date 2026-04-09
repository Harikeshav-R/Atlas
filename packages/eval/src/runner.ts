/**
 * Agent evaluation runner. Discovers fixtures under `fixtures/{agent}/`, runs
 * each through the agent under its pinned reference model, then scores with
 * deterministic assertions + LLM-as-judge. See technical-design.md Section 13.
 */
export async function main(): Promise<void> {
  console.log('[eval] runner stub — no fixtures yet');
}

await main();
