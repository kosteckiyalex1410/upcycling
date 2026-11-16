import { createApiClient, type ApiClient } from '@upcycling/api-client';

import { ApiError, toApiError } from './errors';

/**
 * Same-origin API client (ADR-0005): relative URLs, first-party session cookie.
 * `getLocale` adds `Accept-Language` so server-generated text can follow the UI language.
 */
export function createAppApiClient(getLocale: () => string, baseUrl = ''): ApiClient {
  const client = createApiClient({
    baseUrl,
    credentials: 'same-origin',
    // Resolve fetch lazily so tests can stub it.
    fetch: (request) => globalThis.fetch(request),
  });
  client.use({
    onRequest({ request }) {
      request.headers.set('Accept-Language', getLocale());
      return request;
    },
  });
  return client;
}

type FetchResult<T> = { data?: T; error?: unknown; response: Response };

/**
 * Unwraps an openapi-fetch result: returns data or throws `ApiError` with the
 * server's stable error code. Network failures become `network_error`.
 */
export async function unwrap<T>(call: Promise<FetchResult<T>>): Promise<T> {
  let result: FetchResult<T>;
  try {
    result = await call;
  } catch {
    throw new ApiError('network_error', 0);
  }
  if (!result.response.ok) throw toApiError(result.error, result.response.status);
  return result.data as T;
}
