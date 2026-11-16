import { describe, expect, it, vi } from 'vitest';

import { createAppApiClient, unwrap } from '../../src/shared/api/client';
import { ApiError, errorMessageKey, toApiError } from '../../src/shared/api/errors';
import { EXPERT, json, mockApi } from './harness';

describe('API error handling', () => {
  it('maps the error envelope to a localized message key', () => {
    const error = toApiError({ error: { code: 'rate_limited', message: 'x' } }, 429);
    expect(error).toEqual(expect.objectContaining({ code: 'rate_limited', status: 429 }));
    expect(errorMessageKey(error)).toBe('errors.rate_limited');
  });

  it('falls back to a generic message for unknown codes and non-API errors', () => {
    expect(errorMessageKey(new ApiError('brand_new_code', 400))).toBe('errors.unknown');
    expect(errorMessageKey(new Error('boom'))).toBe('errors.unknown');
    expect(toApiError('not json', 502).code).toBe('unknown');
  });

  it('reports network failures as network_error', async () => {
    vi.stubGlobal('fetch', () => Promise.reject(new TypeError('Failed to fetch')));
    const api = createAppApiClient(() => 'uk', 'http://localhost');
    await expect(unwrap(api.GET('/api/v1/me'))).rejects.toMatchObject({
      code: 'network_error',
      status: 0,
    });
  });

  it('sends the UI language as Accept-Language', async () => {
    const calls = mockApi({ 'GET /api/v1/me': () => json(200, EXPERT) });
    const api = createAppApiClient(() => 'en', 'http://localhost');
    await expect(unwrap(api.GET('/api/v1/me'))).resolves.toEqual(EXPERT);
    expect(calls[0]?.headers.get('Accept-Language')).toBe('en');
  });
});
