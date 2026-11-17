import {
  acceptedContainer,
  microphoneErrorCode,
  pickAudioType,
  recordingSupport,
  type MicrophoneEnv,
  type RecorderErrorCode,
  type RecorderLike,
} from '../../shared/platform/audioRecorder';

/**
 * Voice note recorder state machine (framework-free, ADR-0007):
 *
 *   idle → requesting → recording → recorded → (save | discard) → idle
 *                    ↘ error (permission, no microphone, unsupported…) → idle
 *
 * iOS ends microphone capture when the app goes to the background or the screen locks. We
 * stop on `visibilitychange`/`pagehide`, on a track `ended` event, or when the system stops
 * the recorder, and keep everything captured so far as a finished recording marked
 * `interrupted`: completed audio is never dropped silently. Data is collected every second
 * so an abrupt stop loses at most the last moment.
 */

export const MAX_RECORDING_MS = 5 * 60 * 1000;
export const WARNING_BEFORE_END_MS = 30 * 1000;

export type EndReason = 'user' | 'limit' | 'interrupted';

export type Recording = {
  /** Client upload key: the same recording is never stored twice. */
  id: string;
  blob: Blob;
  /** Object URL for local playback; revoked when the recording is saved or discarded. */
  url: string;
  /** What the browser actually produced, e.g. "audio/mp4; codecs=mp4a.40.2". */
  mimeType: string;
  durationMs: number;
  /** ISO time when recording started (device clock). */
  recordedAt: string;
  endReason: EndReason;
};

export type RecorderState =
  | { status: 'idle' }
  | { status: 'requesting' }
  | { status: 'recording'; elapsedMs: number }
  | { status: 'stopping' }
  | { status: 'recorded'; recording: Recording }
  | { status: 'error'; code: RecorderErrorCode };

/** Subscribes to "the page is being hidden" (backgrounded, locked, closed). */
export type Lifecycle = (onHidden: () => void) => () => void;

const browserLifecycle: Lifecycle = (onHidden) => {
  const visibility = () => {
    if (document.visibilityState === 'hidden') onHidden();
  };
  document.addEventListener('visibilitychange', visibility);
  window.addEventListener('pagehide', onHidden);
  return () => {
    document.removeEventListener('visibilitychange', visibility);
    window.removeEventListener('pagehide', onHidden);
  };
};

type Session = {
  stream: MediaStream;
  recorder: RecorderLike;
  chunks: Blob[];
  startedAt: number;
  recordedAt: string;
  mimeType: string;
  endReason?: EndReason;
  timer: ReturnType<typeof setInterval>;
  unsubscribe: () => void;
};

export class VoiceRecorder {
  private state: RecorderState = { status: 'idle' };
  private session: Session | null = null;
  private listeners = new Set<() => void>();
  private readonly now: () => number;
  private readonly maxMs: number;
  private readonly lifecycle: Lifecycle;
  private readonly tickMs: number;
  private readonly newId: () => string;
  private readonly objectUrls: { create(blob: Blob): string; revoke(url: string): void };

  constructor(
    private readonly env: MicrophoneEnv,
    options: {
      now?: () => number;
      maxMs?: number;
      lifecycle?: Lifecycle;
      tickMs?: number;
      newId?: () => string;
      objectUrls?: { create(blob: Blob): string; revoke(url: string): void };
    } = {},
  ) {
    this.now = options.now ?? (() => Date.now());
    this.newId = options.newId ?? (() => crypto.randomUUID());
    this.objectUrls = options.objectUrls ?? {
      create: (blob) => URL.createObjectURL(blob),
      revoke: (url) => URL.revokeObjectURL(url),
    };
    this.maxMs = options.maxMs ?? MAX_RECORDING_MS;
    this.lifecycle = options.lifecycle ?? browserLifecycle;
    this.tickMs = options.tickMs ?? 250;
  }

  get support() {
    return recordingSupport(this.env);
  }

  subscribe = (listener: () => void): (() => void) => {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  };

  getSnapshot = (): RecorderState => this.state;

  async start(): Promise<void> {
    if (this.state.status !== 'idle' && this.state.status !== 'error') return;
    const support = this.support;
    if (support !== 'supported') {
      this.set({ status: 'error', code: support });
      return;
    }
    this.set({ status: 'requesting' });
    let stream: MediaStream;
    try {
      stream = await this.env.getUserMedia!({ audio: true });
    } catch (error) {
      this.set({ status: 'error', code: microphoneErrorCode(error) });
      return;
    }
    let recorder: RecorderLike;
    try {
      const mimeType = pickAudioType(this.env.isTypeSupported);
      recorder = this.env.createRecorder!(stream, mimeType ? { mimeType } : undefined);
    } catch {
      release(stream);
      this.set({ status: 'error', code: 'format_unsupported' });
      return;
    }
    this.begin(stream, recorder);
  }

  /** Finish recording; the result becomes `recorded` (or `error` if nothing was captured). */
  stop(reason: EndReason = 'user'): void {
    const session = this.session;
    if (!session || this.state.status !== 'recording') return;
    session.endReason = reason;
    this.set({ status: 'stopping' });
    if (session.recorder.state === 'inactive') {
      this.finish(session);
      return;
    }
    try {
      session.recorder.stop(); // `onstop` delivers the last data, then finishes
    } catch {
      this.finish(session);
    }
  }

  /** Done with the finished recording (saved or discarded), or clear an error. */
  reset(): void {
    if (this.state.status === 'recorded') this.objectUrls.revoke(this.state.recording.url);
    if (this.state.status === 'recorded' || this.state.status === 'error') {
      this.set({ status: 'idle' });
    }
  }

  /** Release the microphone without keeping anything (screen closed while recording). */
  dispose(): void {
    if (this.session) this.cleanup(this.session);
    this.session = null;
    if (this.state.status === 'recorded') this.objectUrls.revoke(this.state.recording.url);
    if (this.state.status !== 'idle') this.set({ status: 'idle' });
  }

  private begin(stream: MediaStream, recorder: RecorderLike): void {
    const session: Session = {
      stream,
      recorder,
      chunks: [],
      startedAt: this.now(),
      recordedAt: new Date().toISOString(),
      mimeType: recorder.mimeType,
      timer: setInterval(() => this.tick(), this.tickMs),
      unsubscribe: this.lifecycle(() => this.stop('interrupted')),
    };
    this.session = session;
    recorder.ondataavailable = (event) => {
      if (event.data.size > 0) session.chunks.push(event.data);
    };
    // The system may stop the recorder itself (iOS: backgrounding, a phone call).
    recorder.onstop = () => {
      if (this.state.status === 'recording') session.endReason = 'interrupted';
      this.finish(session);
    };
    recorder.onerror = () => {
      if (this.state.status === 'recording') this.stop('interrupted');
    };
    for (const track of stream.getAudioTracks()) {
      track.addEventListener('ended', () => this.stop('interrupted'));
    }
    try {
      recorder.start(1000);
    } catch {
      this.cleanup(session);
      this.session = null;
      this.set({ status: 'error', code: 'recording_failed' });
      return;
    }
    this.set({ status: 'recording', elapsedMs: 0 });
  }

  private tick(): void {
    const session = this.session;
    if (!session || this.state.status !== 'recording') return;
    const elapsedMs = this.now() - session.startedAt;
    if (elapsedMs >= this.maxMs) this.stop('limit');
    else this.set({ status: 'recording', elapsedMs });
  }

  private finish(session: Session): void {
    if (this.session !== session) return; // already finished
    this.session = null;
    this.cleanup(session);
    const durationMs = Math.min(this.now() - session.startedAt, this.maxMs);
    const mimeType = session.recorder.mimeType || session.mimeType;
    const blob = new Blob(session.chunks, { type: mimeType });
    if (blob.size === 0) {
      this.set({ status: 'error', code: 'recording_failed' });
      return;
    }
    if (!acceptedContainer(mimeType)) {
      this.set({ status: 'error', code: 'format_unsupported' });
      return;
    }
    this.set({
      status: 'recorded',
      recording: {
        id: this.newId(),
        blob,
        url: this.objectUrls.create(blob),
        mimeType,
        durationMs,
        recordedAt: session.recordedAt,
        endReason: session.endReason ?? 'interrupted',
      },
    });
  }

  private cleanup(session: Session): void {
    clearInterval(session.timer);
    session.unsubscribe();
    release(session.stream); // turns off the microphone indicator
  }

  private set(state: RecorderState): void {
    this.state = state;
    for (const listener of this.listeners) listener();
  }
}

function release(stream: MediaStream): void {
  for (const track of stream.getTracks()) track.stop();
}
