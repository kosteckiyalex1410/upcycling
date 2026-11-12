import { useTranslation } from 'react-i18next';

import { errorMessageKey } from '../api/errors';

export function ErrorMessage({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  const { t } = useTranslation();
  return (
    <div role="alert" className="alert">
      <p>{t(errorMessageKey(error))}</p>
      {onRetry && (
        <button type="button" className="button" onClick={onRetry}>
          {t('app.retry')}
        </button>
      )}
    </div>
  );
}
