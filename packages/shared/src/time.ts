/**
 * Centralized time source. Tests override via `setClock`.
 * Never use `Date.now()` or `new Date()` directly elsewhere.
 */
export interface Clock {
  now(): number;
  nowISO(): string;
}

const systemClock: Clock = {
  now: () => Date.now(),
  nowISO: () => new Date().toISOString(),
};

let currentClock: Clock = systemClock;

export function now(): number {
  return currentClock.now();
}

export function nowISO(): string {
  return currentClock.nowISO();
}

export function setClock(clock: Clock): void {
  currentClock = clock;
}

export function resetClock(): void {
  currentClock = systemClock;
}
