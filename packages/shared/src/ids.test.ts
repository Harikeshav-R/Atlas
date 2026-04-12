import { describe, it, expect } from 'vitest';
import { newId } from './ids.ts';

describe('ids', () => {
  it('creates an ID with the correct prefix', () => {
    const id = newId('run');
    expect(id).toMatch(/^run_[0123456789ABCDEFGHJKMNPQRSTVWXYZ]{26}$/);
  });

  it('creates unique IDs', () => {
    const id1 = newId('listing');
    const id2 = newId('listing');
    expect(id1).not.toBe(id2);
  });
});
