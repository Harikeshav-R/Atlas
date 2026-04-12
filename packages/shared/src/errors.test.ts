import { describe, it, expect } from 'vitest';
import { AtlasError, tryCatch, tryCatchSync, ok, err } from './errors.ts';

describe('errors', () => {
  describe('AtlasError', () => {
    it('serializes to JSON', () => {
      const error = new AtlasError('VALIDATION_FAILED', 'Invalid input', { field: 'email' });
      const json = error.toJSON();
      expect(json).toEqual({
        name: 'AtlasError',
        code: 'VALIDATION_FAILED',
        message: 'Invalid input',
        details: { field: 'email' },
      });
    });
  });

  describe('tryCatch', () => {
    it('returns ok for successful promise', async () => {
      const result = await tryCatch(Promise.resolve('success'));
      expect(result).toEqual(ok('success'));
    });

    it('returns err for rejected promise (AtlasError)', async () => {
      const error = new AtlasError('NOT_FOUND', 'Missing file');
      const result = await tryCatch(Promise.reject(error));
      expect(result).toEqual(err(error.toJSON()));
    });

    it('returns err for rejected promise (Generic Error)', async () => {
      const result = await tryCatch(Promise.reject(new Error('Generic failure')));
      expect(result).toEqual(err({
        name: 'AtlasError',
        code: 'INTERNAL',
        message: 'Generic failure',
      }));
    });
  });

  describe('tryCatchSync', () => {
    it('returns ok for successful function', () => {
      const result = tryCatchSync(() => 'success');
      expect(result).toEqual(ok('success'));
    });

    it('returns err for throwing function', () => {
      const result = tryCatchSync(() => {
        throw new Error('Sync failure');
      });
      expect(result).toEqual(err({
        name: 'AtlasError',
        code: 'INTERNAL',
        message: 'Sync failure',
      }));
    });
  });
});
