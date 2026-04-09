export type AtlasErrorCode =
  | 'VALIDATION_FAILED'
  | 'NOT_FOUND'
  | 'PERMISSION_DENIED'
  | 'BUDGET_EXCEEDED'
  | 'APPROVAL_REQUIRED'
  | 'TOOL_ERROR'
  | 'IPC_ERROR'
  | 'INTERNAL';

export interface AtlasErrorJSON {
  readonly name: 'AtlasError';
  readonly code: AtlasErrorCode;
  readonly message: string;
  readonly details?: Readonly<Record<string, unknown>>;
}

export class AtlasError extends Error {
  public override readonly name = 'AtlasError' as const;
  public readonly code: AtlasErrorCode;
  public readonly details?: Readonly<Record<string, unknown>>;

  constructor(code: AtlasErrorCode, message: string, details?: Record<string, unknown>) {
    super(message);
    this.code = code;
    if (details) this.details = Object.freeze({ ...details });
  }

  toJSON(): AtlasErrorJSON {
    return {
      name: this.name,
      code: this.code,
      message: this.message,
      ...(this.details ? { details: this.details } : {}),
    };
  }
}

export type Result<T, E = AtlasErrorJSON> =
  | { readonly ok: true; readonly data: T }
  | { readonly ok: false; readonly error: E };

export const ok = <T>(data: T): Result<T, never> => ({ ok: true, data });
export const err = <E = AtlasErrorJSON>(error: E): Result<never, E> => ({ ok: false, error });
