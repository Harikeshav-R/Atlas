import { describe, it, expect, afterEach } from 'vitest';
import { now, nowISO, setClock, resetClock } from './time.ts';
import type { Clock } from './time.ts';

describe('time', () => {
  afterEach(() => {
    resetClock();
  });

  it('returns current time by default', () => {
    const t1 = now();
    const t2 = Date.now();
    expect(Math.abs(t1 - t2)).toBeLessThan(100);
  });

  it('can be mocked', () => {
    const mockTime = 1234567890000;
    const mockClock: Clock = {
      now: () => mockTime,
      nowISO: () => new Date(mockTime).toISOString(),
    };
    setClock(mockClock);
    expect(now()).toBe(mockTime);
    expect(nowISO()).toBe('2009-02-13T23:31:30.000Z');
  });
});
