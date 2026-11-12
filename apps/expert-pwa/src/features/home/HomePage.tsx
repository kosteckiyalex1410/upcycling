import { useTranslation } from 'react-i18next';

import { useMe } from '../auth/queries';

export function HomePage() {
  const { t } = useTranslation();
  const me = useMe();

  return (
    <main id="main" className="page">
      <h1>{t('home.title')}</h1>
      {me.data && <p>{t('home.greeting', { email: me.data.email })}</p>}
      <p className="empty-state">{t('home.emptyState')}</p>
    </main>
  );
}
