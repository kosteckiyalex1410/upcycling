import type { MediaAsset, MediaCategory, UploadTicketResponse } from '@upcycling/api-client';

import { ApiError } from '../../shared/api/errors';
import type { UploadTransport } from '../../shared/platform/photos';

/**
 * Client side of the upload protocol (ADR-0006), one queue per open garment.
 *
 * Every step is idempotent on the server, so any failure can be retried with the same
 * `clientUploadId`: transient failures (network, 5xx, storage hiccups) are retried
 * automatically with backoff, then offered to the expert as "Retry". The queue lives in
 * memory only: if iOS discards the page, the photos must be selected again (CLAUDE.md §7).
 */

export type UploadPhase = 'queued' | 'hashing' | 'uploading' | 'processing' | 'failed';

export type UploadItem = {
  readonly id: string;
  readonly fileName: string;
  readonly category: MediaCategory;
  readonly phase: UploadPhase;
  /** 0..1 while uploading. */
  readonly progress: number;
  /** Stable error code (localized as `errors.<code>`) when failed. */
  readonly errorCode?: string;
  readonly retryable?: boolean;
};

export type UploadDeps = {
  requestUpload(body: {
    client_upload_id: string;
    category: MediaCategory;
    content_type: string;
    size_bytes: number;
    sha256: string;
    filename: string | null;
  }): Promise<UploadTicketResponse>;
  complete(mediaId: string): Promise<MediaAsset>;
  transport: UploadTransport;
  hash(file: Blob): Promise<string>;
  contentType(file: File): string;
  /** Called once per photo the server finished (ready or rejected). */
  onFinished(media: MediaAsset): void;
  sleep?(ms: number): Promise<void>;
  newId?(): string;
};

type Entry = {
  item: UploadItem;
  file: File;
  clientUploadId: string;
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

export class UploadQueue {
  private entries: Entry[] = [];
  private snapshot: readonly UploadItem[] = [];
  private listeners = new Set<() => void>();
  private controller = new AbortController();

  constructor(
    private readonly deps: UploadDeps,
    private readonly options: { concurrency?: number; backoffMs?: number[] } = {},
  ) {}

  add(files: Iterable<File>, category: MediaCategory): void {
    for (const file of files) {
      const id = this.newId();
      this.entries.push({
        file,
        clientUploadId: this.newId(),
        running: false,
        item: { id, fileName: file.name, category, phase: 'queued', progress: 0 },
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
  }

  /** Stop all work (e.g. the garment screen closed). Unfinished photos stay `pending` on the
   * server, are shown as unfinished, and are cleaned up by the storage sweep. */
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

  get hasActiveUploads(): boolean {
    return this.entries.some((e) => e.item.phase !== 'failed');
  }

  subscribe = (listener: () => void): (() => void) => {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  };

  getSnapshot = (): readonly UploadItem[] => this.snapshot;

  private newId(): string {
    return this.deps.newId?.() ?? crypto.randomUUID();
  }

  private find(id: string): Entry | undefined {
    return this.entries.find((e) => e.item.id === id);
  }

  private publish(): void {
    this.snapshot = this.entries.map((e) => e.item);
    for (const listener of this.listeners) listener();
  }

  private update(entry: Entry, patch: Partial<UploadItem>): void {
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

  private async run(entry: Entry): Promise<void> {
    const backoff = this.options.backoffMs ?? [1000, 3000, 9000];
    for (let attempt = 0; ; attempt += 1) {
      if (this.controller.signal.aborted) return;
      try {
        const media = await this.attempt(entry);
        this.entries = this.entries.filter((e) => e !== entry);
        this.publish();
        this.deps.onFinished(media);
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

  private async attempt(entry: Entry): Promise<MediaAsset> {
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
      this.deps.requestUpload({
        client_upload_id: entry.clientUploadId,
        category: entry.item.category,
        content_type: this.deps.contentType(file),
        size_bytes: file.size,
        sha256: entry.sha256 ?? '',
        filename: file.name || null,
      });

    let ticket = await requestTicket();
    if (ticket.upload) {
      this.update(entry, { phase: 'uploading', progress: 0 });
      const put = (upload: NonNullable<UploadTicketResponse['upload']>) =>
        this.deps.transport.put(
          { url: upload.url, headers: upload.headers, body: file },
          (progress) => this.update(entry, { progress }),
          this.controller.signal,
        );
      let outcome = await put(ticket.upload);
      if (!outcome.ok && outcome.kind === 'expired') {
        ticket = await requestTicket(); // same photo, fresh URL
        if (ticket.upload) outcome = await put(ticket.upload);
      }
      if (!outcome.ok) {
        throw outcome.kind === 'rejected'
          ? new UploadFailure('upload_failed', false)
          : new UploadFailure('network_error', true);
      }
      this.update(entry, { phase: 'processing', progress: 1 });
      return this.deps.complete(ticket.media.id);
    }
    // Already finished on an earlier attempt, or still pending without a URL (not expected).
    return ticket.media.status === 'pending' ? this.deps.complete(ticket.media.id) : ticket.media;
  }
}
