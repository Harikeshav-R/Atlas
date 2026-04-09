import pino from 'pino';

const SECRET_KEYS = ['password', 'token', 'apiKey', 'api_key', 'secret', 'authorization'];

export const rootLogger = pino({
  level: process.env.ATLAS_LOG_LEVEL ?? 'info',
  redact: {
    paths: SECRET_KEYS.flatMap((k) => [k, `*.${k}`, `*.*.${k}`]),
    censor: '[redacted]',
  },
});

export type Logger = pino.Logger;

export function createLogger(component: string, bindings: Record<string, unknown> = {}): Logger {
  return rootLogger.child({ component, ...bindings });
}
