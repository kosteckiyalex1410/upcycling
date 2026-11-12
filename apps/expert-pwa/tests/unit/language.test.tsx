import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';

import { createMemoryPreferenceStore } from '../../src/shared/platform/preferenceStore';
import { EXPERT, json, mockApi, renderApp, unauthenticated } from './harness';

describe('language preference', () => {
  it('switches language before sign-in and remembers it locally', async () => {
    mockApi({ 'GET /api/v1/me': unauthenticated });
    const store = createMemoryPreferenceStore();
    const user = userEvent.setup();
    await renderApp('/login', { store });

    await user.click(await screen.findByRole('radio', { name: 'English' }));
    expect(await screen.findByRole('heading', { name: 'Sign in' })).toBeInTheDocument();
    expect(store.get('locale')).toBe('en');
  });

  it('persists the choice server-side when signed in', async () => {
    const calls = mockApi({
      'GET /api/v1/me': () => json(200, EXPERT),
      'PATCH /api/v1/me': (_request, body) => json(200, { ...EXPERT, ...(body as object) }),
    });
    const user = userEvent.setup();
    await renderApp('/settings');

    await user.click(await screen.findByRole('radio', { name: 'English' }));
    expect(await screen.findByRole('heading', { name: 'Settings' })).toBeInTheDocument();
    await waitFor(() =>
      expect(calls.find((c) => c.method === 'PATCH')?.body).toEqual({ preferred_locale: 'en' }),
    );
  });

  it('applies the server-side preference after sign-in', async () => {
    mockApi({ 'GET /api/v1/me': () => json(200, { ...EXPERT, preferred_locale: 'en' }) });
    const { i18n } = await renderApp('/', { store: createMemoryPreferenceStore() });
    expect(await screen.findByRole('heading', { name: 'My projects' })).toBeInTheDocument();
    expect(i18n.language).toBe('en');
  });
});
