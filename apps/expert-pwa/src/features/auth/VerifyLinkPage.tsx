import { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link, useNavigate } from 'react-router';

import { ErrorMessage } from '../../shared/ui/ErrorMessage';
import { useVerifyToken } from './queries';

function readTokenFromFragment(): string | null {
  return new URLSearchParams(window.location.hash.slice(1)).get('token');
}

function clearFragment() {
  window.history.replaceState(null, '', window.location.pathname + window.location.search);
}

/** Exchanges the single-use token from the URL fragment for a session, exactly once. */
export function VerifyLinkPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const verifyToken = useVerifyToken();
  const [token] = useState(readTokenFromFragment);
  const started = useRef(false);

  useEffect(() => {
    // Guard against React StrictMode's double effect: the token is single-use.
    if (started.current || !token) return;
    started.current = true;
    clearFragment();
    verifyToken.mutate(token, { onSuccess: () => void navigate('/', { replace: true }) });
  }, [navigate, token, verifyToken]);

  const missingToken = token === null;
  return (
    <main id="main" className="page page--narrow">
      <h1>{t('verify.title')}</h1>
      {missingToken && <p role="alert">{t('verify.missingToken')}</p>}
      {verifyToken.isPending && <p className="status">{t('verify.inProgress')}</p>}
      {verifyToken.isError && <ErrorMessage error={verifyToken.error} />}
      {(missingToken || verifyToken.isError) && (
        <Link to="/login" className="button">
          {t('verify.backToLogin')}
        </Link>
      )}
    </main>
  );
}
