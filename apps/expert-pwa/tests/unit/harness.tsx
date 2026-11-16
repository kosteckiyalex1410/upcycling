import { QueryClient } from '@tanstack/react-query';
import { render } from '@testing-library/react';
import { createMemoryRouter } from 'react-router';
import { RouterProvider } from 'react-router/dom';
import { vi } from 'vitest';

import { AppProviders } from '../../src/app/AppProviders';
import { routes } from '../../src/app/routes';
import { createAppApiClient } from '../../src/shared/api/client';
import { createI18n } from '../../src/shared/i18n';
import {
  createMemoryPreferenceStore,
  type PreferenceStore,
} from '../../src/shared/platform/preferenceStore';

export const EXPERT = {
  id: '0192bcd3-6ed2-75d2-9028-b2f12b9980e3',
  email: 'expert@example.com',
  preferred_locale: 'uk' as const,
};

export const unauthenticated = () =>
  json(401, { error: { code: 'unauthenticated', message: '', request_id: 'r', details: [] } });

export function json(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

type Handler = (request: Request, body: unknown) => Response | Promise<Response>;
export type ApiCall = { method: string; path: string; body: unknown; headers: Headers };

/** Stubs `fetch` with handlers keyed by "METHOD /path". Returns the recorded calls. */
export function mockApi(handlers: Record<string, Handler>): ApiCall[] {
  const calls: ApiCall[] = [];
  vi.stubGlobal('fetch', async (request: Request) => {
    const path = new URL(request.url).pathname;
    const text = request.method === 'GET' ? '' : await request.clone().text();
    const body: unknown = text ? JSON.parse(text) : undefined;
    calls.push({ method: request.method, path, body, headers: request.headers });
    const handler = handlers[`${request.method} ${path}`];
    return handler ? handler(request, body) : json(404, { error: { code: 'not_found' } });
  });
  return calls;
}

export async function renderApp(
  path: string,
  { store = createMemoryPreferenceStore() }: { store?: PreferenceStore } = {},
) {
  const i18n = await createI18n(store);
  const services = {
    i18n,
    api: createAppApiClient(() => i18n.language, 'http://localhost'),
    queryClient: new QueryClient({ defaultOptions: { queries: { retry: false } } }),
  };
  const router = createMemoryRouter(routes, { initialEntries: [path] });
  const view = render(
    <AppProviders services={services}>
      <RouterProvider router={router} />
    </AppProviders>,
  );
  return { ...view, router, i18n, store };
}
