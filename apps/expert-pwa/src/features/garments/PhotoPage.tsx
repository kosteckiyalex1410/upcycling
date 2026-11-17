import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link, useNavigate, useParams } from 'react-router';

import type { MediaAsset, MediaCategory } from '@upcycling/api-client';

import { ApiError } from '../../shared/api/errors';
import { ConfirmAction } from '../../shared/ui/ConfirmAction';
import { ErrorMessage } from '../../shared/ui/ErrorMessage';
import { formatBytes, formatDateTime, formatLabel } from '../../shared/ui/format';
import { MEDIA_CATEGORIES } from './categories';
import { useDeleteMedia, useGarment, useUpdateMediaCategory } from './queries';

export function PhotoPage() {
  const { garmentId = '', mediaId = '' } = useParams();
  const { t } = useTranslation();
  const garment = useGarment(garmentId);
  const media = garment.data?.media.find((m) => m.id === mediaId && m.status === 'ready');

  return (
    <main id="main" className="page">
      <Link to={`/garments/${garmentId}`} className="back-link">
        {t('photo.back')}
      </Link>
      {garment.isPending && <p className="status">{t('app.loading')}</p>}
      {garment.isError && (
        <ErrorMessage error={garment.error} onRetry={() => void garment.refetch()} />
      )}
      {garment.isSuccess && !media && <ErrorMessage error={new ApiError('not_found', 404)} />}
      {media && <PhotoDetails garmentId={garmentId} media={media} />}
    </main>
  );
}

function PhotoDetails({ garmentId, media }: { garmentId: string; media: MediaAsset }) {
  const { t, i18n } = useTranslation();
  const navigate = useNavigate();
  const setCategory = useUpdateMediaCategory(garmentId, media.id);
  const remove = useDeleteMedia(garmentId);
  const categoryName = media.category ? t(`categories.${media.category}`) : null;
  // Optimistic: the chip moves on tap; reverts if the server refuses.
  const [choice, setChoice] = useState<MediaCategory | null | undefined>(undefined);
  const selected = choice === undefined ? media.category : choice;
  const choose = (category: MediaCategory | null) => {
    setChoice(category);
    setCategory.mutate(category, { onSettled: () => setChoice(undefined) });
  };

  return (
    <>
      <h1>{categoryName ?? t('photo.title')}</h1>
      {media.preview_url && (
        <img
          className="photo-preview"
          src={media.preview_url}
          alt={categoryName ? t('photo.alt', { category: categoryName }) : t('photo.altPlain')}
        />
      )}

      <fieldset className="chips" disabled={remove.isPending}>
        <legend>{t('photo.category')}</legend>
        {[null, ...MEDIA_CATEGORIES].map((category) => (
          <label key={category ?? 'none'} className="chip">
            <input
              type="radio"
              name="category"
              checked={selected === category}
              onChange={() => choose(category)}
            />
            <span>{category ? t(`categories.${category}`) : t('photo.noCategory')}</span>
          </label>
        ))}
      </fieldset>
      {setCategory.isError && <ErrorMessage error={setCategory.error} />}

      <h2>{t('photo.details')}</h2>
      <dl className="details">
        {media.content_type && (
          <>
            <dt>{t('photo.format')}</dt>
            <dd>{formatLabel(media.content_type)}</dd>
          </>
        )}
        {media.width && media.height && (
          <>
            <dt>{t('photo.dimensions')}</dt>
            <dd>{t('photo.dimensionsValue', { width: media.width, height: media.height })}</dd>
          </>
        )}
        {media.size_bytes != null && (
          <>
            <dt>{t('photo.fileSize')}</dt>
            <dd>{formatBytes(media.size_bytes, i18n.language)}</dd>
          </>
        )}
        {media.original_filename && (
          <>
            <dt>{t('photo.fileName')}</dt>
            <dd>{media.original_filename}</dd>
          </>
        )}
        {media.completed_at && (
          <>
            <dt>{t('photo.uploaded')}</dt>
            <dd>{formatDateTime(media.completed_at, i18n.language)}</dd>
          </>
        )}
      </dl>

      <div className="stack">
        {media.original_url && (
          <a className="button" href={media.original_url} download>
            {t('photo.downloadOriginal')}
          </a>
        )}
        <ConfirmAction
          label={t('photo.delete')}
          warning={t('photo.deleteConfirm')}
          pending={remove.isPending}
          onConfirm={() =>
            remove.mutate(media.id, {
              onSuccess: () => void navigate(`/garments/${garmentId}`, { replace: true }),
            })
          }
        />
        {remove.isError && <ErrorMessage error={remove.error} />}
      </div>
    </>
  );
}
