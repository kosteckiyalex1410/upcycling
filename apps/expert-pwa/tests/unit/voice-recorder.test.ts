import { describe, expect, it, vi } from 'vitest';

import {
  MAX_RECORDING_MS,
  VoiceRecorder,
  type RecorderState,
} from '../../src/features/garments/voiceRecorder';
import {
  acceptedContainer,
  pickAudioType,
  type MicrophoneEnv,
  type RecorderLike,
} from '../../src/shared/platform/audioRecorder';

/** Stands in for MediaRecorder: emits a chunk on stop like the real one. */
class FakeRecorder implements RecorderLike {
  state: 'inactive' | 'recording' | 'paused' = 'inactive';
  ondataavailable: ((event: { data: Blob }) => void) | null = null;
  onstop: (() => void) | null = null;
  onerror: ((event: unknown) => void) | null = null;
  constructor(
    readonly mimeType: string,
    private readonly bytes = 'audio-bytes',
  ) {}
  start() {
    this.state = 'recording';
  }
  stop() {
    this.state = 'inactive';
    this.ondataavailable?.({ data: new Blob([this.bytes]) });
    this.onstop?.();
  }
  /** What iOS does when the app is backgrounded: the system ends the recording. */
  systemStop() {
    this.stop();
  }
}

function fakeStream() {
  const listeners: Record<string, () => void> = {};
  const track = {
    stop: vi.fn(),
    addEventListener: (name: string, fn: () => void) => (listeners[name] = fn),
  };
  const stream = {
    getTracks: () => [track],
    getAudioTracks: () => [track],
  } as unknown as MediaStream;
  return { stream, track, end: () => listeners.ended?.() };
}

function setup(env: Partial<MicrophoneEnv> = {}, recorderBytes = 'audio-bytes') {
  let clock = 1_000;
  let hide: () => void = () => undefined;
  const media = fakeStream();
  let recorder: FakeRecorder | undefined;
  const createRecorder = vi.fn((_: MediaStream, options?: MediaRecorderOptions) => {
    recorder = new FakeRecorder(options?.mimeType ?? 'audio/mp4', recorderBytes);
    return recorder;
  });
  const voice = new VoiceRecorder(
    {
      secure: true,
      getUserMedia: () => Promise.resolve(media.stream),
      isTypeSupported: (type) => type === 'audio/mp4;codecs=mp4a.40.2',
      createRecorder,
      ...env,
    },
    {
      now: () => clock,
      tickMs: 10,
      lifecycle: (onHidden) => {
        hide = onHidden;
        return () => (hide = () => undefined);
      },
      newId: () => 'rec-1',
      objectUrls: { create: () => 'blob:rec-1', revoke: vi.fn() },
    },
  );
  const states: RecorderState['status'][] = [];
  voice.subscribe(() => states.push(voice.getSnapshot().status));
  return {
    voice,
    states,
    media,
    createRecorder,
    recorder: () => recorder!,
    advance: (ms: number) => (clock += ms),
    hide: () => hide(),
  };
}

describe('VoiceRecorder', () => {
  it('records, stops and offers the recording for review', async () => {
    const { voice, states, media, createRecorder, advance } = setup();
    await voice.start();
    expect(createRecorder).toHaveBeenCalledWith(media.stream, {
      mimeType: 'audio/mp4;codecs=mp4a.40.2',
    });
    expect(voice.getSnapshot()).toEqual({ status: 'recording', elapsedMs: 0 });

    advance(42_000);
    voice.stop();
    const state = voice.getSnapshot();
    expect(states).toEqual(['requesting', 'recording', 'stopping', 'recorded']);
    expect(state.status === 'recorded' && state.recording).toMatchObject({
      id: 'rec-1',
      url: 'blob:rec-1',
      mimeType: 'audio/mp4;codecs=mp4a.40.2',
      durationMs: 42_000,
      endReason: 'user',
    });
    expect(media.track.stop).toHaveBeenCalled(); // microphone released
  });

  it('updates the elapsed time and stops itself at the limit', async () => {
    const { voice, advance } = setup();
    await voice.start();
    advance(1_500);
    await vi.waitFor(() => expect(voice.getSnapshot()).toMatchObject({ elapsedMs: 1_500 }));
    advance(MAX_RECORDING_MS);
    await vi.waitFor(() => expect(voice.getSnapshot().status).toBe('recorded'));
    const state = voice.getSnapshot();
    expect(state.status === 'recorded' && state.recording).toMatchObject({
      durationMs: MAX_RECORDING_MS,
      endReason: 'limit',
    });
  });

  it('keeps what was recorded when the app is backgrounded or the screen locks', async () => {
    const { voice, hide, advance } = setup();
    await voice.start();
    advance(5_000);
    hide();
    const state = voice.getSnapshot();
    expect(state.status === 'recorded' && state.recording.endReason).toBe('interrupted');
  });

  it('keeps the recording when the system stops the recorder or the track ends', async () => {
    const first = setup();
    await first.voice.start();
    first.recorder().systemStop();
    expect(first.voice.getSnapshot()).toMatchObject({
      status: 'recorded',
      recording: { endReason: 'interrupted' },
    });

    const second = setup();
    await second.voice.start();
    second.media.end();
    expect(second.voice.getSnapshot()).toMatchObject({
      status: 'recorded',
      recording: { endReason: 'interrupted' },
    });
  });

  it('reports a denied microphone permission and can try again', async () => {
    const denied = Object.assign(new Error('denied'), { name: 'NotAllowedError' });
    const getUserMedia = vi.fn().mockRejectedValueOnce(denied);
    const { voice, media } = setup({ getUserMedia });
    await voice.start();
    expect(voice.getSnapshot()).toEqual({ status: 'error', code: 'permission_denied' });

    getUserMedia.mockResolvedValueOnce(media.stream);
    await voice.start();
    expect(voice.getSnapshot().status).toBe('recording');
  });

  it.each([
    ['NotFoundError', 'no_microphone'],
    ['NotReadableError', 'microphone_busy'],
    ['TypeError', 'recording_failed'],
  ])('maps %s to %s', async (name, code) => {
    const error = Object.assign(new Error(name), { name });
    const { voice } = setup({ getUserMedia: () => Promise.reject(error) });
    await voice.start();
    expect(voice.getSnapshot()).toEqual({ status: 'error', code });
  });

  it('explains when recording is impossible in this browser', async () => {
    const noRecorder = setup({ createRecorder: undefined });
    expect(noRecorder.voice.support).toBe('unsupported');
    await noRecorder.voice.start();
    expect(noRecorder.voice.getSnapshot()).toEqual({ status: 'error', code: 'unsupported' });

    const http = setup({ secure: false });
    await http.voice.start();
    expect(http.voice.getSnapshot()).toEqual({ status: 'error', code: 'insecure' });
  });

  it('rejects formats the server cannot store', async () => {
    const { voice } = setup({
      isTypeSupported: () => false,
      createRecorder: () => new FakeRecorder('audio/ogg;codecs=opus'),
    });
    await voice.start();
    voice.stop();
    expect(voice.getSnapshot()).toEqual({ status: 'error', code: 'format_unsupported' });
  });

  it('treats an empty recording as a failure, not a saved note', async () => {
    const { voice } = setup({}, '');
    await voice.start();
    voice.stop();
    expect(voice.getSnapshot()).toEqual({ status: 'error', code: 'recording_failed' });
  });

  it('discards a reviewed recording and releases everything on dispose', async () => {
    const { voice, media } = setup();
    await voice.start();
    voice.stop();
    voice.reset();
    expect(voice.getSnapshot()).toEqual({ status: 'idle' });

    await voice.start();
    voice.dispose();
    expect(voice.getSnapshot()).toEqual({ status: 'idle' });
    expect(media.track.stop).toHaveBeenCalledTimes(2);
  });
});

describe('audio formats', () => {
  it('prefers MP4/AAC (Safari, iOS), then WebM/Opus (Chrome)', () => {
    expect(pickAudioType((t) => t.startsWith('audio/mp4'))).toBe('audio/mp4;codecs=mp4a.40.2');
    expect(pickAudioType((t) => t.startsWith('audio/webm'))).toBe('audio/webm;codecs=opus');
    expect(pickAudioType(() => false)).toBeUndefined();
    expect(pickAudioType(undefined)).toBeUndefined();
  });

  it.each([
    ['audio/mp4; codecs=mp4a.40.2', 'audio/mp4'],
    ['audio/webm;codecs=opus', 'audio/webm'],
    ['audio/ogg;codecs=opus', null],
    ['video/mp4', null],
  ])('%s -> %s', (mime, expected) => {
    expect(acceptedContainer(mime)).toBe(expected);
  });
});
