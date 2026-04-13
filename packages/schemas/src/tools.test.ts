import { describe, it, expect } from 'vitest';
import { ToolResultSchema } from './tools.ts';

describe('ToolResultSchema', () => {
  it('validates a successful result', () => {
    const data = { ok: true, data: { foo: 'bar' } };
    expect(ToolResultSchema.parse(data)).toEqual(data);
  });

  it('validates an error result', () => {
    const data = { ok: false, error: { code: 'ERR', message: 'Something went wrong' } };
    expect(ToolResultSchema.parse(data)).toEqual(data);
  });

  it('fails on invalid shape', () => {
    const data = { foo: 'bar' };
    expect(() => ToolResultSchema.parse(data)).toThrow();
  });
});
