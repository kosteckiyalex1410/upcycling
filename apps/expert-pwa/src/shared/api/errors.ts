import type { ErrorResponse } from '@upcycling/api-client';

/** Error codes the UI has localized messages for (`errors.<code>`). */
const LOCALIZED_ERROR_CODES = [
  'unauthenticated',
  'invalid_login_token',
  'invalid_login_code',
  'rate_limited',
  'validation_failed',
  'origin_not_allowed',
  'network_error',
  'not_found',
  'internal_error',
] as const;

export type LocalizedErrorCode = (typeof LOCALIZED_ERROR_CODES)[number] | 'unknown';

export class ApiError extends Error {
  constructor(
    readonly code: string,
    readonly status: number,
  ) {
    super(`API error ${status}: ${code}`);
    this.name = 'ApiError';
  }
}

function isErrorResponse(value: unknown): value is ErrorResponse {
  return (
    typeof value === 'object' &&
    value !== null &&
    'error' in value &&
    typeof (value as ErrorResponse).error?.code === 'string'
  );
}

export function toApiError(body: unknown, status: number): ApiError {
  return new ApiError(isErrorResponse(body) ? body.error.code : 'unknown', status);
}

export function errorCodeOf(error: unknown): LocalizedErrorCode {
  const code = error instanceof ApiError ? error.code : 'unknown';
  return (LOCALIZED_ERROR_CODES as readonly string[]).includes(code)
    ? (code as LocalizedErrorCode)
    : 'unknown';
}

export function errorMessageKey(error: unknown) {
  return `errors.${errorCodeOf(error)}` as const;
}
