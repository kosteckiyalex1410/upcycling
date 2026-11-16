import { useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { NavLink, Outlet } from 'react-router';

import { useMe } from '../features/auth/queries';

/** Signed-in shell. Applies the server-side language preference after sign-in. */
export function AppLayout() {
  const { t, i18n } = useTranslation();
  const preferredLocale = useMe().data?.preferred_locale;

  useEffect(() => {
    if (preferredLocale && preferredLocale !== i18n.language) {
      void i18n.changeLanguage(preferredLocale);
    }
    // Only react to server-side changes; local switches update the server themselves.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [preferredLocale]);

  return (
    <>
      <a href="#main" className="skip-link">
        {t('app.skipToContent')}
      </a>
      <header className="app-header">
        <span className="app-header__title">{t('app.name')}</span>
        <nav aria-label={t('nav.primary')}>
          <NavLink to="/" end>
            {t('nav.home')}
          </NavLink>
          <NavLink to="/settings">{t('nav.settings')}</NavLink>
        </nav>
      </header>
      <Outlet />
    </>
  );
}
