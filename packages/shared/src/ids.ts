import { ulid } from 'ulid';

export type IdPrefix =
  | 'run'
  | 'listing'
  | 'application'
  | 'profile'
  | 'story'
  | 'source'
  | 'approval'
  | 'trace'
  | 'event'
  | 'doc'
  | 'snapshot'
  | 'eval'
  | 'scorecard'
  | 'pref'
  | 'cost'
  | 'log';

export type PrefixedId<P extends IdPrefix = IdPrefix> = `${P}_${string}`;

export function newId<P extends IdPrefix>(prefix: P): PrefixedId<P> {
  return `${prefix}_${ulid()}` as PrefixedId<P>;
}
