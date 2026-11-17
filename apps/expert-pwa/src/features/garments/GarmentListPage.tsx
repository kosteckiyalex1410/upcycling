import { useTranslation } from 'react-i18next';
import { Link, useNavigate } from 'react-router';

import { formatDate } from '../../shared/ui/format';
import { ErrorMessage } from '../../shared/ui/ErrorMessage';
import { useCreateGarment, useGarments } from './queries';

export function GarmentListPage() {
  const { t, i18n } = useTranslation();
  const navigate = useNavigate();
  const garments = useGarments();
  const create = useCreateGarment();

  const startProject = () =>
    create.mutate(crypto.randomUUID(), {
      onSuccess: (garment) => void navigate(`/garments/${garment.id}`),
    });

  const items = garments.data?.pages.flatMap((page) => page.items) ?? [];

  return (
    <main id="main" className="page">
      <div className="page-heading">
        <h1>{t('home.title')}</h1>
        <button
          type="button"
          className="button button--primary"
          onClick={startProject}
          disabled={create.isPending}
        >
          {create.isPending ? t('home.creating') : t('home.newGarment')}
        </button>
      </div>
      {create.isError && <ErrorMessage error={create.error} />}

      {garments.isPending && <p className="status">{t('app.loading')}</p>}
      {garments.isError && (
        <ErrorMessage error={garments.error} onRetry={() => void garments.refetch()} />
      )}
      {garments.isSuccess && items.length === 0 && <p className="empty-state">{t('home.empty')}</p>}

      <ul className="garment-list">
        {items.map((garment) => (
          <li key={garment.id}>
            <Link to={`/garments/${garment.id}`} className="garment-card">
              {garment.cover_thumbnail_url ? (
                <img src={garment.cover_thumbnail_url} alt="" className="garment-card__cover" />
              ) : (
                <span className="garment-card__cover garment-card__cover--empty" aria-hidden />
              )}
              <span className="garment-card__text">
                <span className="garment-card__title">
                  {garment.title ?? t('garment.untitled')}
                </span>
                <span className="hint">
                  {t('home.photoCount', { count: garment.photo_count })} ·{' '}
                  {formatDate(garment.created_at, i18n.language)}
                </span>
              </span>
            </Link>
          </li>
        ))}
      </ul>

      {garments.hasNextPage && (
        <button
          type="button"
          className="button"
          onClick={() => void garments.fetchNextPage()}
          disabled={garments.isFetchingNextPage}
        >
          {t('home.loadMore')}
        </button>
      )}
    </main>
  );
}
