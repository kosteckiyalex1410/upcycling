import { useTranslation } from 'react-i18next';
import { useRegisterSW } from 'virtual:pwa-register/react';

/**
 * The service worker precaches only the app shell. New versions wait until the
 * expert chooses to reload, so a stale shell never lingers silently on iOS.
 */
export function UpdatePrompt() {
  const { t } = useTranslation();
  const {
    needRefresh: [needRefresh, setNeedRefresh],
    updateServiceWorker,
  } = useRegisterSW();

  if (!needRefresh) return null;
  return (
    <div role="status" className="update-banner">
      <p>{t('update.available')}</p>
      <button
        type="button"
        className="button button--primary"
        onClick={() => void updateServiceWorker(true)}
      >
        {t('update.reload')}
      </button>
      <button type="button" className="button button--link" onClick={() => setNeedRefresh(false)}>
        {t('update.dismiss')}
      </button>
    </div>
  );
}
