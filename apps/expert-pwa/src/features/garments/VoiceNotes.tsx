import { useTranslation } from 'react-i18next';

import type { VoiceNote } from '@upcycling/api-client';

import { errorKeyForCode } from '../../shared/api/errors';
import { ConfirmAction } from '../../shared/ui/ConfirmAction';
import { ErrorMessage } from '../../shared/ui/ErrorMessage';
import { formatDateTime, formatDuration } from '../../shared/ui/format';
import { MicIcon, StopIcon } from '../../shared/ui/icons';
import { useDeleteVoiceNote } from './queries';
import type { UploadItem } from './uploadQueue';
import type { useVoiceNotes, VoiceMeta } from './useVoiceNotes';
import { MAX_RECORDING_MS, WARNING_BEFORE_END_MS, type Recording } from './voiceRecorder';

type Voice = ReturnType<typeof useVoiceNotes>;

export function RecordButton({ voice }: { voice: Voice }) {
  const { t } = useTranslation();
  return (
    <button
      type="button"
      className="button capture-button capture-button--voice"
      onClick={() => void voice.recorder.start()}
    >
      <MicIcon />
      <span>{t('voice.record')}</span>
    </button>
  );
}

/** Recording controls shown in the bottom bar: status, timer, stop, review, save. */
export function RecorderPanel({ voice }: { voice: Voice }) {
  const { t } = useTranslation();
  const { state } = voice;

  switch (state.status) {
    case 'idle':
      return null;
    case 'requesting':
      return (
        <p role="status" className="recorder__status">
          {t('voice.requesting')}
        </p>
      );
    case 'recording': {
      const remaining = MAX_RECORDING_MS - state.elapsedMs;
      return (
        <div className="recorder">
          <p role="status" className="recorder__status recorder__status--live">
            <span className="recorder__dot" aria-hidden />
            {t('voice.recording')}{' '}
            <span className="recorder__time">
              {t('voice.elapsed', {
                elapsed: formatDuration(state.elapsedMs),
                max: formatDuration(MAX_RECORDING_MS),
              })}
            </span>
          </p>
          {remaining <= WARNING_BEFORE_END_MS && (
            <p className="recorder__warning">
              {t('voice.endingSoon', { seconds: Math.ceil(remaining / 1000) })}
            </p>
          )}
          <button
            type="button"
            className="button button--danger-solid capture-button"
            onClick={() => voice.recorder.stop()}
          >
            <StopIcon />
            <span>{t('voice.stop')}</span>
          </button>
        </div>
      );
    }
    case 'stopping':
      return (
        <p role="status" className="recorder__status">
          {t('voice.finishing')}
        </p>
      );
    case 'recorded':
      return <RecordingReview recording={state.recording} voice={voice} />;
    case 'error':
      return (
        <div className="recorder" role="alert">
          <p className="recorder__status">{t(`voice.errors.${state.code}`)}</p>
          <div className="button-row">
            {state.code !== 'unsupported' && state.code !== 'insecure' && (
              <button
                type="button"
                className="button button--primary"
                onClick={() => void voice.recorder.start()}
              >
                {t('voice.tryAgain')}
              </button>
            )}
            <button type="button" className="button" onClick={() => voice.recorder.reset()}>
              {t('voice.close')}
            </button>
          </div>
        </div>
      );
  }
}

function RecordingReview({ recording, voice }: { recording: Recording; voice: Voice }) {
  const { t } = useTranslation();
  return (
    <div className="recorder">
      <p className="recorder__status">
        {t('voice.reviewTitle', { duration: formatDuration(recording.durationMs) })}
      </p>
      {recording.endReason !== 'user' && (
        <p className="recorder__warning">{t(`voice.ended.${recording.endReason}`)}</p>
      )}
      <audio className="voice-audio" controls src={recording.url} aria-label={t('voice.preview')} />
      <div className="button-row recorder__actions">
        <button type="button" className="button button--primary" onClick={voice.save}>
          {t('voice.save')}
        </button>
        <ConfirmAction
          label={t('voice.discard')}
          warning={t('voice.discardConfirm')}
          onConfirm={voice.discard}
        />
      </div>
    </div>
  );
}

/** Saved voice notes, uploads in progress and recordings not yet saved. */
export function VoiceNoteList({
  garmentId,
  notes,
  voice,
}: {
  garmentId: string;
  notes: VoiceNote[];
  voice: Voice;
}) {
  const { t } = useTranslation();
  const count = notes.filter((n) => n.status === 'ready').length;
  const empty = notes.length === 0 && voice.items.length === 0;
  return (
    <section aria-labelledby="voice-heading" className="garment-section">
      <h2 id="voice-heading">
        {t('voice.heading')} {count > 0 && <span className="count">{count}</span>}
      </h2>
      {empty ? (
        <p className="hint">{t('voice.empty')}</p>
      ) : (
        <ul className="voice-list">
          {notes.map((note, index) => (
            <li key={note.id}>
              <VoiceNoteRow garmentId={garmentId} note={note} number={index + 1} />
            </li>
          ))}
          {voice.items.map((item) => (
            <li key={item.id}>
              <VoiceUploadRow item={item} voice={voice} />
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function VoiceNoteRow({
  garmentId,
  note,
  number,
}: {
  garmentId: string;
  note: VoiceNote;
  number: number;
}) {
  const { t, i18n } = useTranslation();
  const remove = useDeleteVoiceNote(garmentId);
  const title = t('voice.noteTitle', { number });

  if (note.status !== 'ready' || !note.audio_url) {
    return (
      <div className="voice-note voice-note--status" data-status={note.status}>
        <p className="voice-note__title">
          {title} · {note.status === 'rejected' ? t('upload.rejected') : t('upload.unfinished')}
        </p>
        {note.error_code && <p className="hint">{t(errorKeyForCode(note.error_code))}</p>}
        <button
          type="button"
          className="button button--small"
          onClick={() => remove.mutate(note.id)}
          disabled={remove.isPending}
        >
          {t('actions.remove')}
        </button>
      </div>
    );
  }
  const when = note.recorded_at ?? note.created_at;
  return (
    <article className="voice-note" aria-label={title}>
      <p className="voice-note__title">
        {title} · {formatDuration(note.duration_ms ?? 0)}
        <span className="hint"> · {formatDateTime(when, i18n.language)}</span>
      </p>
      <audio
        className="voice-audio"
        controls
        preload="none"
        src={note.audio_url}
        aria-label={t('voice.play', { title })}
      />
      <ConfirmAction
        label={t('voice.delete')}
        warning={t('voice.deleteConfirm')}
        pending={remove.isPending}
        onConfirm={() => remove.mutate(note.id)}
      />
      {remove.isError && <ErrorMessage error={remove.error} />}
    </article>
  );
}

function VoiceUploadRow({ item, voice }: { item: UploadItem<VoiceMeta>; voice: Voice }) {
  const { t } = useTranslation();
  const notSaved = item.errorCode === 'not_saved';
  const percent = Math.round(item.progress * 100);
  const label =
    item.phase === 'uploading'
      ? t('upload.uploading', { percent })
      : notSaved
        ? t('voice.notSaved')
        : item.phase === 'failed'
          ? t('voice.saveFailed')
          : t(`upload.${item.phase}`);

  return (
    <div className="voice-note voice-note--status" data-status={item.phase}>
      <p className="voice-note__title">
        {t('voice.newNote', { duration: formatDuration(item.meta.durationMs) })} · {label}
      </p>
      {item.phase === 'uploading' && (
        <progress max={100} value={percent} aria-label={t('voice.progressLabel')} />
      )}
      {item.phase === 'failed' && (
        <>
          {!notSaved && item.errorCode && (
            <p className="hint">{t(errorKeyForCode(item.errorCode))}</p>
          )}
          <div className="button-row">
            {item.retryable && (
              <button
                type="button"
                className="button button--small button--primary"
                onClick={() => voice.queue.retry(item.id)}
              >
                {notSaved ? t('voice.save') : t('actions.retry')}
              </button>
            )}
          </div>
          {/* Removing loses the only copy of this recording: confirm first. */}
          <ConfirmAction
            label={t('voice.discard')}
            warning={t('voice.discardConfirm')}
            onConfirm={() => voice.queue.remove(item.id)}
          />
        </>
      )}
    </div>
  );
}
