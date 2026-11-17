import type { PresignedUpload } from '@upcycling/api-client';

import { ApiError } from '../../shared/api/errors';
import type { UploadTransport } from '../../shared/platform/photos';

/**
 * Client side of the upload protocol (ADR-0006, ADR-0007), shared by photos and voice
 * notes. One queue per open garment and kind.
 *
 * Every step is idempotent on the server, so any failure can be retried with the same
 * `clientUploadId`: transient failures (network, 5xx, storage hiccups) are retried
 * automatically with backoff, then offered to the expert as "Retry". The queue itself lives
 * in memory; callers that must survive a page reload (voice notes) persist the file and its
 * `clientUploadId` and re-add it later (`held` items wait for the expert's "Save").
 */

export type UploadPhase = 'queued' | 'hashing' | 'uploading' | 'processing' | 'failed';

export type UploadItem<M> = {
  readonly id: string;
  readonly clientUploadId: string;
  readonly fileName: string;
  /** Kind-specific data (photo category, recording duration…). */
  readonly meta: M;
  readonly phase: UploadPhase;
  /** 0..1 while uploading. */
  readonly progress: number;
  /** Stable error code (localized as `errors.<code>`) when failed. */
  readonly errorCode?: string;
  readonly retryable?: boolean;
};

export type UploadRequestBody = {
  client_upload_id: string;
  content_type: string;
  size_bytes: number;
  sha256: string;
  filename: string | null;
};

/** A server record that went through the upload protocol. */
export type Uploaded = { id: string; status: 'pending' | 'ready' | 'rejected' };

export type UploadTicket<R> = { record: R; upload: PresignedUpload | null };

export type UploadDeps<M, R extends Uploaded> = {
  requestUpload(body: UploadRequestBody, meta: M): Promise<UploadTicket<R>>;
  complete(id: string): Promise<R>;
  transport: UploadTransport;
  hash(file: Blob): Promise<string>;
  contentType(file: File): string;
  /** Called once per upload the server finished (ready or rejected). */
  onFinished(record: R, item: UploadItem<M>): void;
  /** Called when the expert removes an item that never finished. */
  onRemoved?(item: UploadItem<M>): void;
  sleep?(ms: number): Promise<void>;
  newId?(): string;
};

type Entry<M> = {
  item: UploadItem<M>;
  file: File;
  sha256?: string;
  running: boolean;
};

class UploadFailure extends Error {
  constructor(
    readonly code: string,
    readonly retryable: boolean,
  ) {
    super(code);
  }
}

// Server errors the expert can fix by waiting/retrying (vs. permanent rejections).
const RETRYABLE_CODES = new Set([
  'network_error',
  'internal_error',
  'storage_unavailable',
  'upload_incomplete',
  'too_many_pending_uploads',
]);

function classify(error: unknown): UploadFailure {
  if (error instanceof UploadFailure) return error;
  if (error instanceof ApiError) {
    return new UploadFailure(error.code, error.status >= 500 || RETRYABLE_CODES.has(error.code));
  }
  return new UploadFailure('unknown', true);
}

const defaultSleep = (ms: number) => new Promise<void>((resolve) => setTimeout(resolve, ms));

export class UploadQueue<M, R extends Uploaded> {
  private entries: Entry<M>[] = [];
  private snapshot: readonly UploadItem<M>[] = [];
  private listeners = new Set<() => void>();
  private controller = new AbortController();

  constructor(
    private readonly deps: UploadDeps<M, R>,
    private readonly options: { concurrency?: number; backoffMs?: number[] } = {},
  ) {}

  /**
   * Queue files for upload. `clientUploadId` resumes an earlier attempt (same server
   * record); `held` adds the item as not yet saved: it waits until `retry`.
   */
  add(
    files: Iterable<File>,
    meta: M,
    options: { clientUploadId?: string; held?: boolean } = {},
  ): void {
    for (const file of files) {
      const clientUploadId = options.clientUploadId ?? this.newId();
      if (this.entries.some((e) => e.item.clientUploadId === clientUploadId)) continue;
      this.entries.push({
        file,
        running: false,
        item: {
          id: this.newId(),
          clientUploadId,
          fileName: file.name,
          meta,
          ...(options.held
            ? { phase: 'failed', errorCode: 'not_saved', retryable: true }
            : { phase: 'queued' }),
          progress: 0,
        },
      });
    }
    this.publish();
    this.pump();
  }

  retry(id: string): void {
    const entry = this.find(id);
    if (entry?.item.phase !== 'failed') return;
    this.update(entry, { phase: 'queued', errorCode: undefined, retryable: undefined });
    this.pump();
  }

  remove(id: string): void {
    const entry = this.find(id);
    if (!entry || entry.running) return;
    this.entries = this.entries.filter((e) => e !== entry);
    this.publish();
    this.deps.onRemoved?.(entry.item);
  }

  /** Stop all work (e.g. the garment screen closed). Unfinished uploads stay `pending` on
   * the server, are shown as unfinished, and are cleaned up by the storage sweep. */
  dispose(): void {
    this.controller.abort();
  }

  /** Re-arm after `dispose` (React StrictMode mounts effects twice in development). */
  activate(): void {
    if (!this.controller.signal.aborted) return;
    this.controller = new AbortController();
    for (const entry of this.entries) {
      if (!entry.running && entry.item.phase !== 'failed') this.update(entry, { phase: 'queued' });
    }
    this.pump();
  }

  subscribe = (listener: () => void): (() => void) => {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  };

  getSnapshot = (): readonly UploadItem<M>[] => this.snapshot;

  private newId(): string {
    return this.deps.newId?.() ?? crypto.randomUUID();
  }

  private find(id: string): Entry<M> | undefined {
    return this.entries.find((e) => e.item.id === id);
  }

  private publish(): void {
    this.snapshot = this.entries.map((e) => e.item);
    for (const listener of this.listeners) listener();
  }

  private update(entry: Entry<M>, patch: Partial<UploadItem<M>>): void {
    entry.item = { ...entry.item, ...patch };
    this.publish();
  }

  private pump(): void {
    const limit = this.options.concurrency ?? 2;
    let running = this.entries.filter((e) => e.running).length;
    for (const entry of this.entries) {
      if (running >= limit) break;
      if (entry.running || entry.item.phase !== 'queued') continue;
      running += 1;
      entry.running = true;
      void this.run(entry).finally(() => {
        entry.running = false;
        this.pump();
      });
    }
  }

  private async run(entry: Entry<M>): Promise<void> {
    const backoff = this.options.backoffMs ?? [1000, 3000, 9000];
    for (let attempt = 0; ; attempt += 1) {
      if (this.controller.signal.aborted) return;
      try {
        const record = await this.attempt(entry);
        this.entries = this.entries.filter((e) => e !== entry);
        this.publish();
        this.deps.onFinished(record, entry.item);
        return;
      } catch (error) {
        if (this.controller.signal.aborted) return;
        const failure = classify(error);
        if (failure.retryable && attempt < backoff.length) {
          await (this.deps.sleep ?? defaultSleep)(backoff[attempt] ?? 0);
          continue;
        }
        this.update(entry, {
          phase: 'failed',
          errorCode: failure.code,
          retryable: failure.retryable,
        });
        return;
      }
    }
  }

  private async attempt(entry: Entry<M>): Promise<R> {
    const { file } = entry;
    if (!entry.sha256) {
      this.update(entry, { phase: 'hashing', progress: 0 });
      try {
        entry.sha256 = await this.deps.hash(file);
      } catch {
        throw new UploadFailure('file_unreadable', false);
      }
    }
    const requestTicket = () =>
      this.deps.requestUpload(
        {
          client_upload_id: entry.item.clientUploadId,
          content_type: this.deps.contentType(file),
          size_bytes: file.size,
          sha256: entry.sha256 ?? '',
          filename: file.name || null,
        },
        entry.item.meta,
      );

    let ticket = await requestTicket();
    if (ticket.upload) {
      this.update(entry, { phase: 'uploading', progress: 0 });
      const put = (upload: PresignedUpload) =>
        this.deps.transport.put(
          { url: upload.url, headers: upload.headers, body: file },
          (progress) => this.update(entry, { progress }),
          this.controller.signal,
        );
      let outcome = await put(ticket.upload);
      if (!outcome.ok && outcome.kind === 'expired') {
        ticket = await requestTicket(); // same record, fresh URL
        if (ticket.upload) outcome = await put(ticket.upload);
      }
      if (!outcome.ok) {
        throw outcome.kind === 'rejected'
          ? new UploadFailure('upload_failed', false)
          : new UploadFailure('network_error', true);
      }
      this.update(entry, { phase: 'processing', progress: 1 });
      return this.deps.complete(ticket.record.id);
    }
    // Already finished on an earlier attempt, or still pending without a URL (not expected).
    return ticket.record.status === 'pending'
      ? this.deps.complete(ticket.record.id)
      : ticket.record;
  }
}
