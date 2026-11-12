import { useState, type FormEvent } from 'react';
import { useTranslation } from 'react-i18next';
import { Navigate, useLocation, useNavigate } from 'react-router';

import { LanguageSwitcher } from '../settings/LanguageSwitcher';
import { ErrorMessage } from '../../shared/ui/ErrorMessage';
import { useMe, useRequestLogin, useVerifyCode } from './queries';

type Challenge = { id: string; email: string; minutesValid: number };

function minutesUntil(isoDate: string): number {
  return Math.max(1, Math.round((new Date(isoDate).getTime() - Date.now()) / 60_000));
}

export function LoginPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const location = useLocation();
  const me = useMe();
  const requestLogin = useRequestLogin();
  const verifyCode = useVerifyCode();
  const [email, setEmail] = useState('');
  const [code, setCode] = useState('');
  const [challenge, setChallenge] = useState<Challenge | null>(null);

  const from = (location.state as { from?: string } | null)?.from ?? '/';
  if (me.data) return <Navigate to={from} replace />;

  function onRequest(event: FormEvent) {
    event.preventDefault();
    const trimmed = email.trim();
    requestLogin.mutate(trimmed, {
      onSuccess: (accepted) =>
        setChallenge({
          id: accepted.challenge_id,
          email: trimmed,
          minutesValid: minutesUntil(accepted.expires_at),
        }),
    });
  }

  function onVerify(event: FormEvent) {
    event.preventDefault();
    if (!challenge) return;
    verifyCode.mutate(
      { challengeId: challenge.id, code },
      { onSuccess: () => void navigate(from, { replace: true }) },
    );
  }

  function reset() {
    setChallenge(null);
    setCode('');
    requestLogin.reset();
    verifyCode.reset();
  }

  return (
    <main id="main" className="page page--narrow">
      <h1>{t('login.title')}</h1>

      {challenge === null ? (
        <form onSubmit={onRequest} className="stack">
          <p>{t('login.intro')}</p>
          <label className="field">
            <span>{t('login.emailLabel')}</span>
            <input
              type="email"
              name="email"
              autoComplete="email"
              inputMode="email"
              autoCapitalize="none"
              required
              value={email}
              onChange={(event) => setEmail(event.target.value)}
            />
          </label>
          {requestLogin.isError && <ErrorMessage error={requestLogin.error} />}
          <button
            type="submit"
            className="button button--primary"
            disabled={requestLogin.isPending}
          >
            {requestLogin.isPending ? t('login.submitting') : t('login.submit')}
          </button>
        </form>
      ) : (
        <form onSubmit={onVerify} className="stack">
          <h2>{t('login.checkEmailTitle')}</h2>
          <p>{t('login.checkEmailBody', { email: challenge.email })}</p>
          <p>{t('login.linkHint')}</p>
          <p>{t('login.codeHint')}</p>
          <label className="field">
            <span>{t('login.codeLabel')}</span>
            <input
              name="code"
              autoComplete="one-time-code"
              inputMode="numeric"
              pattern="[0-9]{6}"
              maxLength={6}
              required
              value={code}
              onChange={(event) => setCode(event.target.value.replace(/\D/g, ''))}
            />
          </label>
          <p className="hint">{t('login.codeValidity', { count: challenge.minutesValid })}</p>
          {verifyCode.isError && <ErrorMessage error={verifyCode.error} />}
          <button type="submit" className="button button--primary" disabled={verifyCode.isPending}>
            {t('login.codeSubmit')}
          </button>
          <button type="button" className="button button--link" onClick={reset}>
            {t('login.useDifferentEmail')}
          </button>
        </form>
      )}

      <LanguageSwitcher />
    </main>
  );
}
