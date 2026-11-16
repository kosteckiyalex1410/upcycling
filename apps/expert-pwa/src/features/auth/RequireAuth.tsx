import { useTranslation } from 'react-i18next';
import { Navigate, Outlet, useLocation } from 'react-router';

import { ErrorMessage } from '../../shared/ui/ErrorMessage';
import { useMe } from './queries';

export function RequireAuth() {
  const { t } = useTranslation();
  const location = useLocation();
  const me = useMe();

  if (me.isPending) return <p className="status">{t('app.loading')}</p>;
  if (me.isError) return <ErrorMessage error={me.error} onRetry={() => void me.refetch()} />;
  if (me.data === null) return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  return <Outlet />;
}
