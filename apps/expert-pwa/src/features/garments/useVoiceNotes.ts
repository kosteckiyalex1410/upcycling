import { useQueryClient } from '@tanstack/react-query';
import { useEffect, useState, useSyncExternalStore } from 'react';

import type { Garment, VoiceNote } from '@upcycling/api-client';

import { useApi } from '../../shared/api/apiContext';
import { unwrap } from '../../shared/api/client';
import { browserMicrophone, type MicrophoneEnv } from '../../shared/platform/audioRecorder';
import { sha256Hex, xhrUploadTransport } from '../../shared/platform/photos';
import {
  indexedDbVoiceDraftStore,
  type VoiceDraft,
  type VoiceDraftStore,
} from '../../shared/platform/voiceDrafts';
import { garmentKey, invalidateGarment } from './queries';
import { UploadQueue } from './uploadQueue';
import { VoiceRecorder, type Recording } from './voiceRecorder';

export type VoiceMeta = { durationMs: number; recordedAt: string };
export type VoiceUploadQueue = UploadQueue<VoiceMeta, VoiceNote>;

/** Platform dependencies; tests replace them. */
export const voicePlatform: { microphone: () => MicrophoneEnv; drafts: () => VoiceDraftStore } = {
  microphone: browserMicrophone,
  drafts: indexedDbVoiceDraftStore,
};

function extension(mimeType: string): string {
  return mimeType.startsWith('audio/webm') ? 'webm' : 'm4a';
}

function draftFile(draft: Pick<VoiceDraft, 'data' | 'mimeType'> | Recording): File {
  const body = 'blob' in draft ? draft.blob : draft.data;
  return new File([body], `voice-note.${extension(draft.mimeType)}`, { type: draft.mimeType });
}

/**
 * Recorder + upload queue for one garment's voice notes (ADR-0007). A finished recording is
 * copied to local drafts at once, so it survives a reload or iOS discarding the page until the
 * server has it; drafts found on open come back as "not saved" items.
 */
export function useVoiceNotes(garmentId: string) {
  const api = useApi();
  const queryClient = useQueryClient();
  const [drafts] = useState(() => voicePlatform.drafts());
  const [recorder] = useState(() => new VoiceRecorder(voicePlatform.microphone()));
  const [queue] = useState(
    () =>
      new UploadQueue<VoiceMeta, VoiceNote>({
        requestUpload: async (body, meta) => {
          const ticket = await unwrap(
            api.POST('/api/v1/garments/{garment_id}/voice-notes/uploads', {
              params: { path: { garment_id: garmentId } },
              body: {
                client_upload_id: body.client_upload_id,
                content_type: body.content_type,
                size_bytes: body.size_bytes,
                sha256: body.sha256,
                duration_ms: Math.round(meta.durationMs),
                recorded_at: meta.recordedAt,
              },
            }),
          );
          return { record: ticket.voice_note, upload: ticket.upload };
        },
        complete: (voiceNoteId) =>
          unwrap(
            api.POST('/api/v1/garments/{garment_id}/voice-notes/complete', {
              params: { path: { garment_id: garmentId } },
              body: { voice_note_id: voiceNoteId },
            }),
          ),
        transport: xhrUploadTransport,
        hash: sha256Hex,
        contentType: (file) => file.type,
        onFinished: (note, item) => {
          void drafts.remove(item.clientUploadId);
          queryClient.setQueryData<Garment>(garmentKey(garmentId), (garment) =>
            garment
              ? {
                  ...garment,
                  voice_notes: [...garment.voice_notes.filter((n) => n.id !== note.id), note],
                }
              : garment,
          );
          invalidateGarment(queryClient, garmentId);
        },
        onRemoved: (item) => void drafts.remove(item.clientUploadId),
      }),
  );

  // Recordings left from an earlier visit (not yet on the server) wait for "Save".
  useEffect(() => {
    let cancelled = false;
    void drafts.list(garmentId).then((found) => {
      if (cancelled) return;
      for (const draft of found) {
        queue.add(
          [draftFile(draft)],
          { durationMs: draft.durationMs, recordedAt: draft.recordedAt },
          { clientUploadId: draft.clientUploadId, held: true },
        );
      }
    });
    return () => {
      cancelled = true;
    };
  }, [drafts, garmentId, queue]);

  useEffect(() => {
    queue.activate();
    return () => {
      queue.dispose();
      recorder.dispose();
    };
  }, [queue, recorder]);

  const state = useSyncExternalStore(recorder.subscribe, recorder.getSnapshot);
  const items = useSyncExternalStore(queue.subscribe, queue.getSnapshot);

  // Keep a local copy of every finished recording until it is saved or discarded.
  useEffect(() => {
    if (state.status !== 'recorded') return;
    const { recording } = state;
    recording.blob
      .arrayBuffer()
      .then((data) =>
        drafts.put({
          clientUploadId: recording.id,
          garmentId,
          data,
          mimeType: recording.mimeType,
          durationMs: recording.durationMs,
          recordedAt: recording.recordedAt,
        }),
      )
      .catch(() => undefined); // best effort: the in-memory recording still works
  }, [drafts, garmentId, state]);

  const save = () => {
    if (state.status !== 'recorded') return;
    const { recording } = state;
    queue.add(
      [draftFile(recording)],
      { durationMs: recording.durationMs, recordedAt: recording.recordedAt },
      { clientUploadId: recording.id },
    );
    recorder.reset();
  };

  const discard = () => {
    if (state.status === 'recorded') void drafts.remove(state.recording.id);
    recorder.reset();
  };

  return {
    recorder,
    state,
    queue,
    items,
    save,
    discard,
    busy:
      state.status === 'recording' ||
      state.status === 'recorded' ||
      items.some((item) => item.phase !== 'failed'),
  };
}
