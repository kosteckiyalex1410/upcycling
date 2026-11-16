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
  'unsupported_media_type',
  'upload_too_large',
  'image_too_large',
  'invalid_image',
  'checksum_mismatch',
  'media_limit_reached',
  'too_many_pending_uploads',
  'upload_incomplete',
  'storage_unavailable',
  'idempotency_conflict',
  'upload_failed',
  'file_unreadable',
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
  return localizedCode(error instanceof ApiError ? error.code : 'unknown');
}

/** Maps any stable code (API error or photo `error_code`) to one the UI can display. */
export function localizedCode(code: string): LocalizedErrorCode {
  return (LOCALIZED_ERROR_CODES as readonly string[]).includes(code)
    ? (code as LocalizedErrorCode)
    : 'unknown';
}

export function errorMessageKey(error: unknown) {
  return `errors.${errorCodeOf(error)}` as const;
}

export function errorKeyForCode(code: string) {
  return `errors.${localizedCode(code)}` as const;
}
