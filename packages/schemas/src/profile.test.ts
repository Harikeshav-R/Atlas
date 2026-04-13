import { describe, it, expect } from 'vitest';
import { ProfileSchema } from './profile.ts';

describe('ProfileSchema', () => {
  it('validates a minimal valid profile', () => {
    const profile = {
      version: 1,
      name: 'John Doe',
      contact: {
        email: 'john@example.com',
      },
    };
    const result = ProfileSchema.parse(profile);
    expect(result.name).toBe('John Doe');
    expect(result.experience).toEqual([]);
    expect(result.preferences.remote).toBe('any');
  });

  it('fails on missing required fields', () => {
    const profile = {
      version: 1,
      name: 'John Doe',
    };
    expect(() => ProfileSchema.parse(profile)).toThrow();
  });
});
