/**
 * Wrap scraped / external content with tamper-resistant markers before
 * handing it to an LLM. The harness enforces that all scraped content flows
 * through this helper. See technical-design.md Section 12.
 */
export function wrapUntrusted(content: string, source: string): string {
  return [
    `<untrusted_content source="${escapeAttr(source)}">`,
    content,
    `</untrusted_content>`,
  ].join('\n');
}

function escapeAttr(s: string): string {
  return s.replace(/[<>"'&]/g, (c) => `&#${c.charCodeAt(0)};`);
}
