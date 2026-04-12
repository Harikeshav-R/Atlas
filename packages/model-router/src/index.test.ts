import { describe, it, expect } from 'vitest';
import { ModelRouter } from './index.ts';

describe('ModelRouter Phase 0', () => {
  it('returns hardcoded OpenRouter models for stages', () => {
    const router = new ModelRouter({ getPricing: () => undefined });
    expect(router.getModelId('triage')).toBe('openrouter/google/gemini-2.5-flash-lite');
    expect(router.getModelId('evaluation')).toBe('openrouter/google/gemini-2.5-flash');
    
    const model = router.getModel('triage');
    expect(model).toBeDefined();
    expect(model).toHaveProperty('provider');
    expect((model as { provider: string }).provider).toContain('openrouter');
  });

  it('calculates cost from pricing lookup', () => {
    const getPricing = (id: string) => {
      if (id === 'openrouter/google/gemini-2.5-flash') {
        return {
          prompt_token_cost_usd_per_million: 3.0,
          output_token_cost_usd_per_million: 15.0,
        };
      }
      return undefined;
    };
    const router = new ModelRouter({ getPricing });

    const cost = router.calculateCost('openrouter/google/gemini-2.5-flash', 1000, 500);
    // (1000 / 1M) * 3 + (500 / 1M) * 15 = 0.003 + 0.0075 = 0.0105
    expect(cost).toBeCloseTo(0.0105);

    const unknownCost = router.calculateCost('unknown', 1000, 1000);
    expect(unknownCost).toBe(0);
  });
});
