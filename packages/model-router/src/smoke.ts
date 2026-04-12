import { ModelRouter } from './index.ts';
import { generateText } from 'ai';

async function main() {
  const apiKey = process.env.OPENROUTER_API_KEY;
  if (!apiKey) {
    console.error('Error: OPENROUTER_API_KEY environment variable is not set.');
    process.exit(1);
  }

  const router = new ModelRouter({
    openRouterApiKey: apiKey,
    getPricing: (modelId) => {
      // Mock pricing for the smoke test
      return {
        prompt_token_cost_usd_per_million: 0.1,
        output_token_cost_usd_per_million: 0.4,
      };
    }
  });

  const stage = 'triage';
  const modelId = router.getModelId(stage);
  console.log(`Testing stage "${stage}" using model: ${modelId}...`);

  try {
    const { text, usage } = await generateText({
      model: router.getModel(stage),
      prompt: 'Say "OpenRouter connection successful!"',
    });

    console.log('\nResponse:', text);
    console.log('Usage:', usage);
    
    const cost = router.calculateCost(modelId, usage.inputTokens ?? 0, usage.outputTokens ?? 0);
    console.log('Calculated Cost:', cost.toFixed(6), 'USD');
    console.log('\n✅ Test passed!');
  } catch (error: any) {
    console.error('\n❌ Test failed!');
    console.error(error.message);
    process.exit(1);
  }
}

main().catch(console.error);
