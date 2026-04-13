/**
 * Simple TTL cache for fetched URLs within a session.
 */
export class FetchCache {
  private readonly entries = new Map<string, { value: string; expiresAt: number }>();
  private readonly ttlMs: number;

  constructor(ttlMs = 5 * 60 * 1000) {
    this.ttlMs = ttlMs;
  }

  get(url: string): string | undefined {
    const entry = this.entries.get(url);
    if (!entry) return undefined;
    if (Date.now() > entry.expiresAt) {
      this.entries.delete(url);
      return undefined;
    }
    return entry.value;
  }

  set(url: string, value: string): void {
    this.entries.set(url, { value, expiresAt: Date.now() + this.ttlMs });
  }
}
