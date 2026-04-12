import { createAnthropic } from '@ai-sdk/anthropic';
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
  readonly anthropicApiKey?: string;
  readonly getPricing: PricingLookup;
}

/**
 * Thin wrapper around the Vercel AI SDK providing stage-based routing and
 * cost accounting. Phase 0 hardcodes Anthropic models.
 */
export class ModelRouter {
  private readonly anthropic;

  // Hard-coded mapping for Phase 0
  private readonly mapping: Record<Stage, string> = {
    triage: 'claude-3-haiku-20240307',
    evaluation: 'claude-3-5-sonnet-latest',
    generation: 'claude-3-5-sonnet-latest',
    verification: 'claude-3-haiku-20240307',
    navigation: 'claude-3-5-sonnet-latest',
    interaction: 'claude-3-haiku-20240307',
  };

  constructor(private readonly config: ModelRouterConfig) {
    this.anthropic = createAnthropic({
      apiKey: this.config.anthropicApiKey ?? 'dummy-key-for-tests',
    });
  }

  getModel(stage: Stage): LanguageModel {
    const modelId = this.mapping[stage];
    return this.anthropic(modelId!);
  }

  getModelId(stage: Stage): string {
    return `anthropic/${this.mapping[stage]}`;
  }

  calculateCost(modelId: string, promptTokens: number, outputTokens: number): number {
    const pricing = this.config.getPricing(modelId);
    if (!pricing) return 0;

    const promptCost = (promptTokens / 1_000_000) * pricing.prompt_token_cost_usd_per_million;
    const outputCost = (outputTokens / 1_000_000) * pricing.output_token_cost_usd_per_million;
    return promptCost + outputCost;
  }
}
