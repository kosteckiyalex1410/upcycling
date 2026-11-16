import { useEffect, useState, type FormEvent } from 'react';
import { useTranslation } from 'react-i18next';
import { Link, useBlocker, useNavigate, useParams } from 'react-router';

import type { Garment, MediaAsset, MediaCategory } from '@upcycling/api-client';

import { errorKeyForCode } from '../../shared/api/errors';
import { PhotoPicker } from '../../shared/platform/PhotoPicker';
import { ConfirmAction } from '../../shared/ui/ConfirmAction';
import { ErrorMessage } from '../../shared/ui/ErrorMessage';
import { formatDate } from '../../shared/ui/format';
import { MEDIA_CATEGORIES } from './categories';
import { useDeleteGarment, useDeleteMedia, useGarment, useUpdateGarment } from './queries';
import type { UploadItem, UploadQueue } from './uploadQueue';
import { useUploadQueue } from './useUploadQueue';

export function GarmentPage() {
  const { garmentId = '' } = useParams();
  const garment = useGarment(garmentId);
  const { t } = useTranslation();

  return (
    <main id="main" className="page">
      <Link to="/" className="back-link">
        {t('garment.back')}
      </Link>
      {garment.isPending && <p className="status">{t('app.loading')}</p>}
      {garment.isError && (
        <ErrorMessage error={garment.error} onRetry={() => void garment.refetch()} />
      )}
      {garment.data && <GarmentEditor garment={garment.data} />}
    </main>
  );
}

function GarmentEditor({ garment }: { garment: Garment }) {
  const { t, i18n } = useTranslation();
  const navigate = useNavigate();
  const uploads = useUploadQueue(garment.id);
  const remove = useDeleteGarment(garment.id);

  // Leaving stops unfinished uploads: ask first (in-app navigation and tab close/reload).
  const blocker = useBlocker(uploads.active);
  useEffect(() => {
    if (!uploads.active) return;
    const warn = (event: BeforeUnloadEvent) => event.preventDefault();
    window.addEventListener('beforeunload', warn);
    return () => window.removeEventListener('beforeunload', warn);
  }, [uploads.active]);

  return (
    <>
      <h1>{garment.title ?? t('garment.untitled')}</h1>
      <p className="hint">
        {t('garment.createdOn', { date: formatDate(garment.created_at, i18n.language) })}
      </p>

      {blocker.state === 'blocked' && (
        <div role="alertdialog" aria-label={t('garment.leaveTitle')} className="confirm">
          <p>
            <strong>{t('garment.leaveTitle')}</strong> {t('garment.leaveBody')}
          </p>
          <div className="button-row">
            <button type="button" className="button" onClick={() => blocker.reset()}>
              {t('garment.stay')}
            </button>
            <button
              type="button"
              className="button button--danger"
              onClick={() => blocker.proceed()}
            >
              {t('garment.leave')}
            </button>
          </div>
        </div>
      )}

      <section aria-labelledby="photos-heading">
        <h2 id="photos-heading">{t('garment.photos')}</h2>
        {MEDIA_CATEGORIES.map((category) => (
          <CategorySection
            key={category}
            category={category}
            garmentId={garment.id}
            media={garment.media.filter((m) => m.category === category)}
            uploads={uploads.items.filter((item) => item.category === category)}
            queue={uploads.queue}
          />
        ))}
      </section>

      <GarmentDetailsForm key={garment.id} garment={garment} />

      <section className="danger-zone">
        <ConfirmAction
          label={t('garment.delete')}
          warning={t('garment.deleteConfirm')}
          pending={remove.isPending}
          onConfirm={() =>
            remove.mutate(undefined, { onSuccess: () => void navigate('/', { replace: true }) })
          }
        />
        {remove.isError && <ErrorMessage error={remove.error} />}
      </section>
    </>
  );
}

function CategorySection({
  category,
  garmentId,
  media,
  uploads,
  queue,
}: {
  category: MediaCategory;
  garmentId: string;
  media: MediaAsset[];
  uploads: UploadItem[];
  queue: UploadQueue;
}) {
  const { t } = useTranslation();
  const headingId = `category-${category}`;
  const empty = media.length === 0 && uploads.length === 0;

  return (
    <section className="category" aria-labelledby={headingId}>
      <div className="category__header">
        <h3 id={headingId}>{t(`categories.${category}`)}</h3>
        <p className="hint">{t(`categoryHints.${category}`)}</p>
      </div>
      {empty ? null : (
        <ul className="photo-grid">
          {media.map((item) => (
            <li key={item.id}>
              <MediaTile garmentId={garmentId} media={item} />
            </li>
          ))}
          {uploads.map((item) => (
            <li key={item.id}>
              <UploadTile item={item} queue={queue} />
            </li>
          ))}
        </ul>
      )}
      <PhotoPicker
        cameraLabel={t('garment.takePhoto')}
        libraryLabel={t('garment.choosePhotos')}
        onFiles={(files) => queue.add(files, category)}
      />
    </section>
  );
}

function MediaTile({ garmentId, media }: { garmentId: string; media: MediaAsset }) {
  const { t } = useTranslation();
  const remove = useDeleteMedia(garmentId);

  if (media.status === 'ready' && media.thumbnail_url) {
    return (
      <Link
        to={`/garments/${garmentId}/photos/${media.id}`}
        className="photo-tile"
        aria-label={t('garment.openPhoto', { category: t(`categories.${media.category}`) })}
      >
        <img src={media.thumbnail_url} alt="" loading="lazy" />
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

function UploadTile({ item, queue }: { item: UploadItem; queue: UploadQueue }) {
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

function GarmentDetailsForm({ garment }: { garment: Garment }) {
  const { t } = useTranslation();
  const update = useUpdateGarment(garment.id);
  const [title, setTitle] = useState(garment.title ?? '');
  const [notes, setNotes] = useState(garment.notes ?? '');
  const dirty = title.trim() !== (garment.title ?? '') || notes.trim() !== (garment.notes ?? '');

  const submit = (event: FormEvent) => {
    event.preventDefault();
    update.mutate({ title: title.trim() || null, notes: notes.trim() || null });
  };

  return (
    <form className="stack details-form" onSubmit={submit} aria-labelledby="details-heading">
      <h2 id="details-heading">{t('garment.details')}</h2>
      <label className="field">
        {t('garment.titleLabel')}
        <input
          value={title}
          maxLength={120}
          placeholder={t('garment.titlePlaceholder')}
          onChange={(event) => setTitle(event.target.value)}
        />
      </label>
      <label className="field">
        {t('garment.notesLabel')}
        <textarea
          value={notes}
          maxLength={4000}
          rows={4}
          onChange={(event) => setNotes(event.target.value)}
        />
      </label>
      <div className="button-row">
        <button
          type="submit"
          className="button button--primary"
          disabled={!dirty || update.isPending}
        >
          {update.isPending ? t('actions.saving') : t('actions.save')}
        </button>
        {update.isSuccess && !dirty && (
          <span role="status" className="status">
            {t('actions.saved')}
          </span>
        )}
      </div>
      {update.isError && <ErrorMessage error={update.error} />}
    </form>
  );
}
