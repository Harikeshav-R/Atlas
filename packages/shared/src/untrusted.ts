/**
 * Wraps untrusted content in standard markers for the LLM.
 * See docs/02-agent-runtime.md Section 12 for the threat model.
 */
function escapeAttr(s: string): string {
  return s.replace(/[<>"'&]/g, (c) => `&#${c.charCodeAt(0)};`);
}

export function wrapUntrusted(
  content: string,
  source: string,
  url?: string,
): string {
  const urlAttr = url ? ` url="${escapeAttr(url)}"` : '';
  return `<untrusted_content source="${escapeAttr(source)}"${urlAttr}>\n${content}\n</untrusted_content>`;
}
