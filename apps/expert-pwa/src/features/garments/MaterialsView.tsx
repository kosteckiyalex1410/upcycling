import { useState, type FormEvent } from 'react';
import { useTranslation } from 'react-i18next';

import type { Garment, MediaCategory } from '@upcycling/api-client';

import { PhotoPicker } from '../../shared/platform/PhotoPicker';
import { ErrorMessage } from '../../shared/ui/ErrorMessage';
import { CategoryChips } from './CategoryChips';
import { PhotoGallery } from './PhotoGallery';
import { useUpdateGarment } from './queries';
import type { useUploadQueue } from './useUploadQueue';
import type { useVoiceNotes } from './useVoiceNotes';
import { RecordButton, RecorderPanel, VoiceNoteList } from './VoiceNotes';

type Photos = ReturnType<typeof useUploadQueue>;
type Voice = ReturnType<typeof useVoiceNotes>;

/**
 * "Materials" of a design project: photos (captured per category), voice and text notes.
 * The project screen is a header plus one view; AI Ideas and History views (Slices 3–4)
 * are added next to this one, not inside it (ARCHITECTURE.md §9).
 */
export function MaterialsView({
  garment,
  photos,
  voice,
}: {
  garment: Garment;
  photos: Photos;
  voice: Voice;
}) {
  return (
    <>
      <PhotoCapture garment={garment} photos={photos} />
      <NotesSection garment={garment} voice={voice} />
      {voice.state.status !== 'idle' && <RecorderDock voice={voice} />}
    </>
  );
}

function PhotoCapture({ garment, photos }: { garment: Garment; photos: Photos }) {
  const { t } = useTranslation();
  // Stays selected until changed: front → shoot → back → shoot … (default: front).
  const [category, setCategory] = useState<MediaCategory | null>('front');
  const ready = garment.media.filter((m) => m.status === 'ready').length;

  return (
    <section aria-labelledby="photos-heading" className="materials-section">
      <h2 id="photos-heading" className="section-title">
        {t('garment.photos')} {ready > 0 && <span className="count">{ready}</span>}
      </h2>
      <CategoryChips
        name="capture-category"
        legend={t('garment.captureCategory')}
        hideLegend
        scroll
        value={category}
        onChange={setCategory}
      />
      <div className="capture-actions">
        <PhotoPicker
          cameraLabel={t('garment.takePhoto')}
          libraryLabel={t('garment.choosePhotos')}
          onFiles={(files) => photos.queue.add(files, { category })}
        />
      </div>
      <PhotoGallery
        garmentId={garment.id}
        media={garment.media}
        uploads={photos.items}
        queue={photos.queue}
      />
    </section>
  );
}

function NotesSection({ garment, voice }: { garment: Garment; voice: Voice }) {
  const { t } = useTranslation();
  return (
    <section aria-labelledby="notes-heading" className="materials-section">
      <div className="section-head">
        <h2 id="notes-heading" className="section-title">
          {t('garment.notes')}
        </h2>
        <RecordButton voice={voice} />
      </div>
      <VoiceNoteList garmentId={garment.id} notes={garment.voice_notes} voice={voice} />
      <TextNote key={garment.id} garment={garment} />
    </section>
  );
}

/** While recording or reviewing, the controls stay at the bottom edge, within thumb reach. */
function RecorderDock({ voice }: { voice: Voice }) {
  const { t } = useTranslation();
  return (
    <div className="recorder-dock" role="region" aria-label={t('voice.recorderLabel')}>
      <RecorderPanel voice={voice} />
    </div>
  );
}

function TextNote({ garment }: { garment: Garment }) {
  const { t } = useTranslation();
  const update = useUpdateGarment(garment.id);
  const [notes, setNotes] = useState(garment.notes ?? '');
  const [open, setOpen] = useState(Boolean(garment.notes));
  const dirty = notes.trim() !== (garment.notes ?? '');

  const submit = (event: FormEvent) => {
    event.preventDefault();
    update.mutate({ notes: notes.trim() || null });
  };

  return (
    <details
      className="text-note"
      open={open}
      onToggle={(event) => setOpen(event.currentTarget.open)}
    >
      <summary>{t('garment.textNote')}</summary>
      <form className="stack" onSubmit={submit}>
        <label className="field">
          <span className="visually-hidden">{t('garment.textNote')}</span>
          <textarea
            value={notes}
            maxLength={4000}
            rows={3}
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
