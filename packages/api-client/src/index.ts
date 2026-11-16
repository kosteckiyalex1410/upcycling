import createClient, { type ClientOptions } from 'openapi-fetch';

import type { components, paths } from './schema';

export type { components, paths };
export type ApiSchemas = components['schemas'];
export type ErrorResponse = ApiSchemas['ErrorResponse'];
export type Locale = ApiSchemas['Locale'];
export type Me = ApiSchemas['MeResponse'];

/** Framework-neutral typed client for `/api/v1` (ADR-0004). */
export function createApiClient(options: ClientOptions = {}) {
  return createClient<paths>(options);
}

export type ApiClient = ReturnType<typeof createApiClient>;
