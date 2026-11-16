import { useTranslation } from 'react-i18next';

import { useMe, useUpdatePreferredLocale } from '../auth/queries';
import { SUPPORTED_LOCALES, currentLocale, type AppLocale } from '../../shared/i18n';

/**
 * Switches the UI language immediately; when signed in, also persists it as the
 * user's `preferred_locale` so it follows them across devices and sessions.
 */
export function LanguageSwitcher() {
  const { t, i18n } = useTranslation();
  const me = useMe();
  const updateLocale = useUpdatePreferredLocale();
  const active = currentLocale(i18n);

  function choose(locale: AppLocale) {
    if (locale === active) return;
    void i18n.changeLanguage(locale);
    if (me.data) updateLocale.mutate(locale);
  }

  return (
    <fieldset className="language-switcher">
      <legend>{t('settings.language')}</legend>
      {SUPPORTED_LOCALES.map((locale) => (
        <label key={locale} className="choice">
          <input
            type="radio"
            name="locale"
            value={locale}
            checked={active === locale}
            onChange={() => choose(locale)}
          />
          <span lang={locale}>{t(`languages.${locale}`)}</span>
        </label>
      ))}
      {updateLocale.isError && <p role="alert">{t('settings.languageSaveFailed')}</p>}
    </fieldset>
  );
}
