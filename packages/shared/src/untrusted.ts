/**
 * Wraps untrusted content in standard markers for the LLM.
 * See docs/02-agent-runtime.md Section 12 for the threat model.
 */
export function wrapUntrusted(
  content: string,
  source: string,
  url?: string,
): string {
  const urlAttr = url ? ` url="${url}"` : '';
  return `<untrusted_content source="${source}"${urlAttr}>\n${content}\n</untrusted_content>`;
}
