import { describe, test, expect } from 'vitest';
import { computeWeightedScore, scoreToGrade, DEFAULT_WEIGHTS, SCORING_DIMENSIONS } from './schemas.ts';

describe('computeWeightedScore', () => {
  test('computes weighted total from dimension scores', () => {
    const dimensions = SCORING_DIMENSIONS.map((dimension) => ({
      dimension,
      score: 8,
      justification: 'Good fit',
    }));

    const result = computeWeightedScore(dimensions);
    // All scores are 8, all weights sum to 1.0, so weighted total = 8.0
    expect(result).toBe(8);
  });

  test('applies different weights correctly', () => {
    const dimensions = SCORING_DIMENSIONS.map((dimension) => ({
      dimension,
      score: dimension === 'role_skill_alignment' ? 10 : 5,
      justification: 'Test',
    }));

    const result = computeWeightedScore(dimensions);
    // role_skill_alignment: 10 * 0.18 = 1.8
    // all others: 5 * (1.0 - 0.18) = 5 * 0.82 = 4.1
    // total: 1.8 + 4.1 = 5.9
    expect(result).toBe(5.9);
  });
});

describe('scoreToGrade', () => {
  test('maps scores to correct letter grades', () => {
    expect(scoreToGrade(9.5)).toBe('A');
    expect(scoreToGrade(8.5)).toBe('A');
    expect(scoreToGrade(8.4)).toBe('B');
    expect(scoreToGrade(7.0)).toBe('B');
    expect(scoreToGrade(6.9)).toBe('C');
    expect(scoreToGrade(5.5)).toBe('C');
    expect(scoreToGrade(5.4)).toBe('D');
    expect(scoreToGrade(4.0)).toBe('D');
    expect(scoreToGrade(3.9)).toBe('F');
    expect(scoreToGrade(0)).toBe('F');
  });
});

describe('DEFAULT_WEIGHTS', () => {
  test('weights sum to 1.0', () => {
    const total = Object.values(DEFAULT_WEIGHTS).reduce((sum, w) => sum + w, 0);
    expect(total).toBeCloseTo(1.0, 10);
  });

  test('has exactly 10 dimensions', () => {
    expect(Object.keys(DEFAULT_WEIGHTS)).toHaveLength(10);
  });
});
