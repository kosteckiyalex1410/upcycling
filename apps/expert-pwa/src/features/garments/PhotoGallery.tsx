import { useTranslation } from 'react-i18next';
import { Link } from 'react-router';

import type { MediaAsset } from '@upcycling/api-client';

import { errorKeyForCode } from '../../shared/api/errors';
import { useDeleteMedia } from './queries';
import type { UploadItem } from './uploadQueue';
import type { PhotoMeta, PhotoUploadQueue } from './useUploadQueue';

/** All photos of a project in one grid, with their category and upload state. */
export function PhotoGallery({
  garmentId,
  media,
  uploads,
  queue,
}: {
  garmentId: string;
  media: MediaAsset[];
  uploads: readonly UploadItem<PhotoMeta>[];
  queue: PhotoUploadQueue;
}) {
  const { t } = useTranslation();
  if (media.length === 0 && uploads.length === 0) {
    return <p className="hint empty">{t('garment.noPhotos')}</p>;
  }
  return (
    <ul className="photo-grid">
      {media.map((item, index) => (
        <li key={item.id}>
          <MediaTile garmentId={garmentId} media={item} number={index + 1} />
        </li>
      ))}
      {uploads.map((item) => (
        <li key={item.id}>
          <UploadTile item={item} queue={queue} />
        </li>
      ))}
    </ul>
  );
}

function MediaTile({
  garmentId,
  media,
  number,
}: {
  garmentId: string;
  media: MediaAsset;
  number: number;
}) {
  const { t } = useTranslation();
  const remove = useDeleteMedia(garmentId);

  if (media.status === 'ready' && media.thumbnail_url) {
    const category = media.category ? t(`categories.${media.category}`) : null;
    return (
      <Link
        to={`/garments/${garmentId}/photos/${media.id}`}
        className="photo-tile"
        aria-label={
          category
            ? t('garment.openPhotoCategory', { number, category })
            : t('garment.openPhoto', { number })
        }
      >
        <img src={media.thumbnail_url} alt="" loading="lazy" />
        {category && (
          <span className="photo-tile__chip" aria-hidden>
            {category}
          </span>
        )}
      </Link>
    );
  }
  // Rejected photo, or an upload that was interrupted in an earlier session.
  return (
    <div className="photo-tile photo-tile--status" data-status={media.status}>
      <span className="photo-tile__label">
        {media.status === 'rejected' ? t('upload.rejected') : t('upload.unfinished')}
      </span>
      {media.error_code && (
        <span className="photo-tile__detail">{t(errorKeyForCode(media.error_code))}</span>
      )}
      <button
        type="button"
        className="button button--small"
        onClick={() => remove.mutate(media.id)}
        disabled={remove.isPending}
      >
        {t('actions.remove')}
      </button>
    </div>
  );
}

function UploadTile({ item, queue }: { item: UploadItem<PhotoMeta>; queue: PhotoUploadQueue }) {
  const { t } = useTranslation();
  const percent = Math.round(item.progress * 100);
  const label =
    item.phase === 'uploading'
      ? t('upload.uploading', { percent })
      : item.phase === 'failed'
        ? t('upload.failed')
        : t(`upload.${item.phase}`);

  return (
    <div className="photo-tile photo-tile--status" data-status={item.phase}>
      <span className="photo-tile__label">{label}</span>
      {item.phase === 'uploading' && (
        <progress
          max={100}
          value={percent}
          aria-label={t('upload.progressLabel', { name: item.fileName })}
        />
      )}
      {item.phase === 'failed' && (
        <>
          {item.errorCode && (
            <span className="photo-tile__detail">{t(errorKeyForCode(item.errorCode))}</span>
          )}
          <div className="button-row">
            {item.retryable && (
              <button
                type="button"
                className="button button--small"
                onClick={() => queue.retry(item.id)}
              >
                {t('actions.retry')}
              </button>
            )}
            <button
              type="button"
              className="button button--small"
              onClick={() => queue.remove(item.id)}
            >
              {t('actions.remove')}
            </button>
          </div>
        </>
      )}
    </div>
  );
}
