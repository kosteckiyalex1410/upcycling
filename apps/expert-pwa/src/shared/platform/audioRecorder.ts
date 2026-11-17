/**
 * Microphone platform adapter (ARCHITECTURE.md §9 `AudioRecorderPort`), browser
 * implementation over `getUserMedia` + `MediaRecorder`. A native shell can provide the same
 * shape without touching feature code.
 *
 * Browsers record different formats: Safari/iOS produces MP4 with AAC, Chrome WebM with Opus
 * (newer Chrome can also do MP4). We ask for the first supported type in
 * `PREFERRED_AUDIO_TYPES` and then trust only `recorder.mimeType`, never our request.
 */

export const PREFERRED_AUDIO_TYPES = [
  'audio/mp4;codecs=mp4a.40.2',
  'audio/mp4',
  'audio/webm;codecs=opus',
  'audio/webm',
] as const;

/** Containers the server accepts (ADR-0007). */
const ACCEPTED_CONTAINERS = new Set(['audio/mp4', 'audio/webm']);

export type RecordingSupport = 'supported' | 'insecure' | 'unsupported';

export type RecorderErrorCode =
  | 'permission_denied'
  | 'no_microphone'
  | 'microphone_busy'
  | 'unsupported'
  | 'insecure'
  | 'format_unsupported'
  | 'recording_failed';

/** The subset of `MediaRecorder` the feature uses (easy to fake in tests). */
export interface RecorderLike {
  readonly mimeType: string;
  readonly state: 'inactive' | 'recording' | 'paused';
  start(timeslice?: number): void;
  stop(): void;
  ondataavailable: ((event: { data: Blob }) => void) | null;
  onstop: (() => void) | null;
  onerror: ((event: unknown) => void) | null;
}

export interface MicrophoneEnv {
  /** `window.isSecureContext`: the microphone needs HTTPS (or localhost). */
  secure: boolean;
  getUserMedia?: (constraints: MediaStreamConstraints) => Promise<MediaStream>;
  isTypeSupported?: (type: string) => boolean;
  createRecorder?: (stream: MediaStream, options?: MediaRecorderOptions) => RecorderLike;
}

export function browserMicrophone(): MicrophoneEnv {
  const devices = typeof navigator === 'undefined' ? undefined : navigator.mediaDevices;
  const Recorder = typeof MediaRecorder === 'undefined' ? undefined : MediaRecorder;
  return {
    secure: typeof window !== 'undefined' && window.isSecureContext,
    getUserMedia: devices?.getUserMedia ? (c) => devices.getUserMedia(c) : undefined,
    isTypeSupported: Recorder?.isTypeSupported
      ? (type) => Recorder.isTypeSupported(type)
      : undefined,
    createRecorder: Recorder
      ? (stream, options) => new Recorder(stream, options) as unknown as RecorderLike
      : undefined,
  };
}

export function recordingSupport(env: MicrophoneEnv): RecordingSupport {
  if (!env.secure) return 'insecure';
  return env.getUserMedia && env.createRecorder ? 'supported' : 'unsupported';
}

/** First preferred type the browser can record, or undefined to let it choose. */
export function pickAudioType(isTypeSupported?: (type: string) => boolean): string | undefined {
  if (!isTypeSupported) return undefined;
  return PREFERRED_AUDIO_TYPES.find((type) => {
    try {
      return isTypeSupported(type);
    } catch {
      return false;
    }
  });
}

/** Base container of a recorder MIME type if the server accepts it ("audio/mp4; codecs=…"). */
export function acceptedContainer(mimeType: string): string | null {
  const base = mimeType.split(';', 1)[0]?.trim().toLowerCase() ?? '';
  return ACCEPTED_CONTAINERS.has(base) ? base : null;
}

export function microphoneErrorCode(error: unknown): RecorderErrorCode {
  const name = error instanceof Error || error instanceof DOMException ? error.name : '';
  switch (name) {
    case 'NotAllowedError':
    case 'SecurityError':
      return 'permission_denied';
    case 'NotFoundError':
    case 'OverconstrainedError':
      return 'no_microphone';
    case 'NotReadableError':
    case 'AbortError':
      return 'microphone_busy'; // e.g. a phone call or another app holds the microphone
    default:
      return 'recording_failed';
  }
}
