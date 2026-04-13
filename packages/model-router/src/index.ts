import { createOpenRouter } from '@openrouter/ai-sdk-provider';
import type { LanguageModel } from 'ai';

export type Stage =
  | 'triage'
  | 'evaluation'
  | 'generation'
  | 'verification'
  | 'navigation'
  | 'interaction';

export interface Pricing {
  readonly prompt_token_cost_usd_per_million: number;
  readonly output_token_cost_usd_per_million: number;
}

export type PricingLookup = (modelId: string) => Pricing | undefined;

export interface ModelRouterConfig {
  readonly openRouterApiKey?: string;
  readonly getPricing: PricingLookup;
}

/**
 * Thin wrapper around the Vercel AI SDK providing stage-based routing and
 * cost accounting. Phase 0 hardcodes OpenRouter models.
 */
export class ModelRouter {
  private readonly openrouter;

  // Hard-coded mapping for Phase 0
  private readonly mapping: Record<Stage, string> = {
    triage: 'google/gemini-2.5-flash-lite',
    evaluation: 'google/gemini-2.5-flash',
    generation: 'google/gemini-2.5-flash',
    verification: 'google/gemini-2.5-flash-lite',
    navigation: 'google/gemini-2.5-flash',
    interaction: 'google/gemini-2.5-flash-lite',
  };

  constructor(private readonly config: ModelRouterConfig) {
    this.openrouter = createOpenRouter({
      apiKey: this.config.openRouterApiKey ?? 'dummy-key-for-tests',
    });
  }

  getModel(stage: Stage): LanguageModel {
    const modelId = this.mapping[stage];
    return this.openrouter(modelId!);
  }

  getModelId(stage: Stage): string {
    return `openrouter/${this.mapping[stage]}`;
  }

  calculateCost(modelId: string, promptTokens: number, outputTokens: number): number {
    const pricing = this.config.getPricing(modelId);
    if (!pricing) return 0;

    const promptCost = (promptTokens / 1_000_000) * pricing.prompt_token_cost_usd_per_million;
    const outputCost = (outputTokens / 1_000_000) * pricing.output_token_cost_usd_per_million;
    return promptCost + outputCost;
  }
}
