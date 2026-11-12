import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router';

import { useLogout } from '../auth/queries';
import { ErrorMessage } from '../../shared/ui/ErrorMessage';
import { LanguageSwitcher } from './LanguageSwitcher';

export function SettingsPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const logout = useLogout();
  const logoutEverywhere = useLogout({ everywhere: true });
  const goToLogin = () => void navigate('/login', { replace: true });

  return (
    <main id="main" className="page">
      <h1>{t('settings.title')}</h1>
      <LanguageSwitcher />

      <section className="stack">
        <h2>{t('settings.account')}</h2>
        {logout.isError && <ErrorMessage error={logout.error} />}
        {logoutEverywhere.isError && <ErrorMessage error={logoutEverywhere.error} />}
        <button
          type="button"
          className="button"
          disabled={logout.isPending}
          onClick={() => logout.mutate(undefined, { onSuccess: goToLogin })}
        >
          {t('settings.signOut')}
        </button>
        <button
          type="button"
          className="button button--danger"
          disabled={logoutEverywhere.isPending}
          onClick={() => logoutEverywhere.mutate(undefined, { onSuccess: goToLogin })}
        >
          {t('settings.signOutEverywhere')}
        </button>
        <p className="hint">{t('settings.signOutEverywhereHint')}</p>
      </section>
    </main>
  );
}
