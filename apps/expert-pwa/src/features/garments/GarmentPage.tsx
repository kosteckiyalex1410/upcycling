import { useEffect, useState, type FormEvent } from 'react';
import { useTranslation } from 'react-i18next';
import { Link, useBlocker, useNavigate, useParams } from 'react-router';

import type { Garment, MediaAsset } from '@upcycling/api-client';

import { errorKeyForCode } from '../../shared/api/errors';
import { PhotoPicker } from '../../shared/platform/PhotoPicker';
import { ConfirmAction } from '../../shared/ui/ConfirmAction';
import { ErrorMessage } from '../../shared/ui/ErrorMessage';
import { formatDate } from '../../shared/ui/format';
import { useDeleteGarment, useDeleteMedia, useGarment, useUpdateGarment } from './queries';
import type { UploadItem } from './uploadQueue';
import { useUploadQueue, type PhotoMeta, type PhotoUploadQueue } from './useUploadQueue';
import { useVoiceNotes } from './useVoiceNotes';
import { RecordButton, RecorderPanel, VoiceNoteList } from './VoiceNotes';

export function GarmentPage() {
  const { garmentId = '' } = useParams();
  const garment = useGarment(garmentId);
  const { t } = useTranslation();

  return (
    <main id="main" className="page page--with-bar">
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

/**
 * Camera-first project screen: one photo gallery, voice notes, then the optional name and
 * text notes. Capture actions live in a bar at the bottom edge, within thumb reach.
 */
function GarmentEditor({ garment }: { garment: Garment }) {
  const { t, i18n } = useTranslation();
  const navigate = useNavigate();
  const photos = useUploadQueue(garment.id);
  const voice = useVoiceNotes(garment.id);
  const remove = useDeleteGarment(garment.id);

  // Leaving stops unfinished uploads and recordings: ask first (in-app navigation and
  // tab close/reload).
  const busy = photos.active || voice.busy;
  const blocker = useBlocker(busy);
  useEffect(() => {
    if (!busy) return;
    const warn = (event: BeforeUnloadEvent) => event.preventDefault();
    window.addEventListener('beforeunload', warn);
    return () => window.removeEventListener('beforeunload', warn);
  }, [busy]);

  return (
    <>
      <header className="garment-header">
        <h1>{garment.title ?? t('garment.untitled')}</h1>
        <p className="hint">
          {t('garment.createdOn', { date: formatDate(garment.created_at, i18n.language) })}
        </p>
      </header>

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

      <PhotoGallery
        garmentId={garment.id}
        media={garment.media}
        uploads={photos.items}
        queue={photos.queue}
      />

      <VoiceNoteList garmentId={garment.id} notes={garment.voice_notes} voice={voice} />

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

      <div className="capture-bar" role="toolbar" aria-label={t('garment.captureBar')}>
        {/* While recording or reviewing, the recorder replaces the capture buttons. */}
        {voice.state.status !== 'idle' ? (
          <RecorderPanel voice={voice} />
        ) : (
          <div className="capture-bar__actions">
            <PhotoPicker
              cameraLabel={t('garment.takePhoto')}
              libraryLabel={t('garment.choosePhotos')}
              onFiles={(files) => photos.queue.add(files, { category: null })}
            />
            <RecordButton voice={voice} />
          </div>
        )}
      </div>
    </>
  );
}

function PhotoGallery({
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
  const ready = media.filter((m) => m.status === 'ready').length;
  const empty = media.length === 0 && uploads.length === 0;

  return (
    <section aria-labelledby="photos-heading" className="garment-section">
      <h2 id="photos-heading">
        {t('garment.photos')} {ready > 0 && <span className="count">{ready}</span>}
      </h2>
      {empty ? (
        <p className="hint">{t('garment.noPhotos')}</p>
      ) : (
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
      )}
    </section>
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

function GarmentDetailsForm({ garment }: { garment: Garment }) {
  const { t } = useTranslation();
  const update = useUpdateGarment(garment.id);
  const [title, setTitle] = useState(garment.title ?? '');
  const [notes, setNotes] = useState(garment.notes ?? '');
  // Open by default only when there is something to read.
  const [open, setOpen] = useState(Boolean(garment.notes));
  const dirty = title.trim() !== (garment.title ?? '') || notes.trim() !== (garment.notes ?? '');

  const submit = (event: FormEvent) => {
    event.preventDefault();
    update.mutate({ title: title.trim() || null, notes: notes.trim() || null });
  };

  return (
    <details
      className="garment-section details-panel"
      open={open}
      onToggle={(event) => setOpen(event.currentTarget.open)}
    >
      <summary>{t('garment.details')}</summary>
      <form className="stack" onSubmit={submit}>
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
            placeholder={t('garment.notesPlaceholder')}
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
    </details>
  );
}
