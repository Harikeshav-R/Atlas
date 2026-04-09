export type Stage =
  | 'triage'
  | 'evaluation'
  | 'generation'
  | 'verification'
  | 'navigation'
  | 'interaction';

export interface ModelRouterConfig {
  readonly mapping: Readonly<Record<Stage, { readonly provider: string; readonly model: string }>>;
}

/**
 * Thin wrapper around the Vercel AI SDK providing stage-based routing and
 * cost accounting. Real implementation lands with harness integration.
 */
export class ModelRouter {
  constructor(private readonly config: ModelRouterConfig) {}

  resolve(stage: Stage): { provider: string; model: string } {
    return this.config.mapping[stage];
  }
}
