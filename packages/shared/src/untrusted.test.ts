import { describe, it, expect } from 'vitest';
import { wrapUntrusted } from './untrusted.ts';

describe('untrusted', () => {
  it('wraps content with source', () => {
    const wrapped = wrapUntrusted('content', 'source');
    expect(wrapped).toBe('<untrusted_content source="source">\ncontent\n</untrusted_content>');
  });

  it('wraps content with source and url', () => {
    const wrapped = wrapUntrusted('content', 'source', 'https://example.com');
    expect(wrapped).toBe('<untrusted_content source="source" url="https://example.com">\ncontent\n</untrusted_content>');
  });
});
