/**
 * Per-domain rate limiter. Enforces a minimum delay between requests
 * to the same domain.
 */
export class RateLimiter {
  private readonly timestamps = new Map<string, number>();
  private readonly minDelayMs: number;

  constructor(minDelayMs = 2000) {
    this.minDelayMs = minDelayMs;
  }

  async waitForDomain(domain: string): Promise<void> {
    const last = this.timestamps.get(domain) ?? 0;
    const elapsed = Date.now() - last;
    if (elapsed < this.minDelayMs) {
      await new Promise((resolve) => setTimeout(resolve, this.minDelayMs - elapsed));
    }
    this.timestamps.set(domain, Date.now());
  }
}
