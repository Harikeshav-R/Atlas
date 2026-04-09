import type { Profile } from '@atlas/schemas';

export interface RenderedDocument {
  readonly html: string;
  readonly css: string;
}

export function renderCv(_profile: Profile): RenderedDocument {
  // TODO: real templates under `templates/cv/*.html`
  return { html: '<html></html>', css: '' };
}

export function renderCoverLetter(_profile: Profile, _listingId: string): RenderedDocument {
  return { html: '<html></html>', css: '' };
}
