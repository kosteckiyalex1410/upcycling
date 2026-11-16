import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';

import { EXPERT, json, mockApi, renderApp, unauthenticated } from './harness';

const CHALLENGE = '0192bcd4-0fd5-78a4-9157-cf9c62d2f017';
const inFifteenMinutes = () => new Date(Date.now() + 15 * 60_000).toISOString();

describe('sign-in', () => {
  it('redirects to the localized login page when signed out', async () => {
    mockApi({ 'GET /api/v1/me': unauthenticated });
    const { router } = await renderApp('/');
    expect(await screen.findByRole('heading', { name: 'Вхід' })).toBeInTheDocument();
    expect(router.state.location.pathname).toBe('/login');
  });

  it('requests a login email and signs in with the one-time code', async () => {
    let signedIn = false;
    const calls = mockApi({
      'GET /api/v1/me': () => (signedIn ? json(200, EXPERT) : unauthenticated()),
      'POST /api/v1/auth/login-requests': () =>
        json(202, { challenge_id: CHALLENGE, expires_at: inFifteenMinutes() }),
      [`POST /api/v1/auth/login-requests/${CHALLENGE}/verify-code`]: () => {
        signedIn = true;
        return json(200, EXPERT);
      },
    });
    const user = userEvent.setup();
    const { router } = await renderApp('/login');

    await user.type(await screen.findByLabelText('Електронна адреса'), ' expert@example.com ');
    await user.click(screen.getByRole('button', { name: 'Отримати посилання' }));

    expect(await screen.findByRole('heading', { name: 'Перевірте пошту' })).toBeInTheDocument();
    expect(screen.getByText(/дійсні 15 хвилин\./)).toBeInTheDocument();
    expect(calls.find((c) => c.method === 'POST')?.body).toEqual({ email: 'expert@example.com' });

    await user.type(screen.getByLabelText('Код із листа'), '12-34 56');
    await user.click(screen.getByRole('button', { name: 'Увійти' }));

    expect(await screen.findByRole('heading', { name: 'Мої проєкти' })).toBeInTheDocument();
    expect(router.state.location.pathname).toBe('/');
    const verify = calls.find((c) => c.path.endsWith('/verify-code'));
    expect(verify?.body).toEqual({ code: '123456' });
  });

  it('shows a localized error for a wrong code', async () => {
    mockApi({
      'GET /api/v1/me': unauthenticated,
      'POST /api/v1/auth/login-requests': () =>
        json(202, { challenge_id: CHALLENGE, expires_at: inFifteenMinutes() }),
      [`POST /api/v1/auth/login-requests/${CHALLENGE}/verify-code`]: () =>
        json(400, { error: { code: 'invalid_login_code', message: '', details: [] } }),
    });
    const user = userEvent.setup();
    await renderApp('/login');
    await user.type(await screen.findByLabelText('Електронна адреса'), 'expert@example.com');
    await user.click(screen.getByRole('button', { name: 'Отримати посилання' }));
    await user.type(await screen.findByLabelText('Код із листа'), '000000');
    await user.click(screen.getByRole('button', { name: 'Увійти' }));
    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Код недійсний, прострочений або вже використаний.',
    );
  });

  it('exchanges the magic-link token from the URL fragment exactly once', async () => {
    let signedIn = false;
    const calls = mockApi({
      'GET /api/v1/me': () => (signedIn ? json(200, EXPERT) : unauthenticated()),
      'POST /api/v1/auth/login-requests/verify-token': () => {
        signedIn = true;
        return json(200, EXPERT);
      },
    });
    window.history.replaceState(null, '', '/auth/verify#token=abcdefghijklmnopqrstuvwxyz');
    await renderApp('/auth/verify');

    expect(await screen.findByRole('heading', { name: 'Мої проєкти' })).toBeInTheDocument();
    const verifications = calls.filter((c) => c.path.endsWith('/verify-token'));
    expect(verifications).toHaveLength(1);
    expect(verifications[0]?.body).toEqual({ token: 'abcdefghijklmnopqrstuvwxyz' });
    expect(window.location.hash).toBe('');
  });

  it('explains an incomplete magic link', async () => {
    mockApi({ 'GET /api/v1/me': unauthenticated });
    await renderApp('/auth/verify');
    expect(await screen.findByRole('alert')).toHaveTextContent('Посилання неповне');
  });

  it('signs out and returns to the login page', async () => {
    let signedIn = true;
    mockApi({
      'GET /api/v1/me': () => (signedIn ? json(200, EXPERT) : unauthenticated()),
      'POST /api/v1/auth/logout': () => {
        signedIn = false;
        return new Response(null, { status: 204 });
      },
    });
    const user = userEvent.setup();
    const { router } = await renderApp('/settings');
    await user.click(await screen.findByRole('button', { name: 'Вийти' }));
    await waitFor(() => expect(router.state.location.pathname).toBe('/login'));
  });
});
