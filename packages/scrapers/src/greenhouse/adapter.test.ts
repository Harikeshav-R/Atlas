import { describe, test, expect, vi, beforeEach, afterEach } from 'vitest';
import { GreenhouseAdapter } from './adapter.ts';
import listFixture from './__fixtures__/list-response.json';
import detailFixture from './__fixtures__/job-detail.json';

describe('GreenhouseAdapter', () => {
  const adapter = new GreenhouseAdapter();
  let fetchSpy: ReturnType<typeof vi.spyOn<typeof globalThis, 'fetch'>>;

  beforeEach(() => {
    fetchSpy = vi.spyOn(globalThis, 'fetch').mockRejectedValue(new Error('unmocked fetch'));
  });

  afterEach(() => {
    fetchSpy.mockRestore();
  });

  describe('list', () => {
    test('parses Greenhouse board API response into DiscoveredListing[]', async () => {
      fetchSpy.mockResolvedValueOnce(new Response(JSON.stringify(listFixture), { status: 200 }));

      const results = await adapter.list({ companySlug: 'acme' });

      expect(results).toHaveLength(3);
      expect(results[0]).toEqual({
        canonicalUrl: 'https://boards.greenhouse.io/acme/jobs/12345',
        companyName: 'acme',
        roleTitle: 'Senior Software Engineer',
        location: 'San Francisco, CA',
        remoteModel: 'unknown',
      });
      expect(results[1]?.remoteModel).toBe('remote');
      expect(results[2]?.remoteModel).toBe('hybrid');
    });

    test('throws on non-200 response', async () => {
      fetchSpy.mockResolvedValueOnce(new Response('Not Found', { status: 404 }));

      await expect(adapter.list({ companySlug: 'nonexistent' }))
        .rejects.toThrow('HTTP 404');
    });
  });

  describe('fetch', () => {
    test('fetches job detail and extracts markdown', async () => {
      fetchSpy.mockResolvedValueOnce(new Response(JSON.stringify(detailFixture), { status: 200 }));

      const result = await adapter.fetch('https://boards.greenhouse.io/acme/jobs/12345');

      expect(result.canonicalUrl).toBe('https://boards.greenhouse.io/acme/jobs/12345');
      expect(result.roleTitle).toBe('Senior Software Engineer');
      expect(result.descriptionMarkdown).toContain('Senior Software Engineer');
      expect(result.descriptionMarkdown).toContain('5+ years of experience with TypeScript');
      expect(result.descriptionHtml).toContain('<h2>');
    });

    test('throws for invalid URL format', async () => {
      await expect(adapter.fetch('https://example.com/not-greenhouse'))
        .rejects.toThrow('Cannot extract Greenhouse job ID');
    });
  });

  describe('canonicalize', () => {
    test('strips query params and trailing slashes', () => {
      expect(adapter.canonicalize('https://boards.greenhouse.io/acme/jobs/12345?gh_jid=12345'))
        .toBe('https://boards.greenhouse.io/acme/jobs/12345');
    });

    test('strips trailing slash', () => {
      expect(adapter.canonicalize('https://boards.greenhouse.io/acme/jobs/12345/'))
        .toBe('https://boards.greenhouse.io/acme/jobs/12345');
    });

    test('preserves well-formed URLs', () => {
      expect(adapter.canonicalize('https://boards.greenhouse.io/acme/jobs/12345'))
        .toBe('https://boards.greenhouse.io/acme/jobs/12345');
    });
  });
});
