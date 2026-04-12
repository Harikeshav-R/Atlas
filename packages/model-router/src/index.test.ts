import { describe, it, expect } from 'vitest';
import { ModelRouter } from './index.ts';

describe('ModelRouter Phase 0', () => {
  it('returns hardcoded Anthropic models for stages', () => {
    const router = new ModelRouter({ getPricing: () => undefined });
    expect(router.getModelId('triage')).toBe('anthropic/claude-3-haiku-20240307');
    expect(router.getModelId('evaluation')).toBe('anthropic/claude-3-5-sonnet-latest');
    
    const model = router.getModel('triage');
    expect(model).toBeDefined();
    expect((model as any).provider).toContain('anthropic');
  });

  it('calculates cost from pricing lookup', () => {
    const getPricing = (id: string) => {
      if (id === 'anthropic/claude-3-5-sonnet-latest') {
        return {
          prompt_token_cost_usd_per_million: 3.0,
          output_token_cost_usd_per_million: 15.0,
        };
      }
      return undefined;
    };
    const router = new ModelRouter({ getPricing });

    const cost = router.calculateCost('anthropic/claude-3-5-sonnet-latest', 1000, 500);
    // (1000 / 1M) * 3 + (500 / 1M) * 15 = 0.003 + 0.0075 = 0.0105
    expect(cost).toBeCloseTo(0.0105);

    const unknownCost = router.calculateCost('unknown', 1000, 1000);
    expect(unknownCost).toBe(0);
  });
});
