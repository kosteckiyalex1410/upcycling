import { describe, expect, it, vi } from 'vitest';

import type { MediaAsset } from '@upcycling/api-client';

import {
  UploadQueue,
  type UploadDeps,
  type UploadTicket,
} from '../../src/features/garments/uploadQueue';
import { ApiError } from '../../src/shared/api/errors';
import { declaredContentType, type UploadOutcome } from '../../src/shared/platform/photos';

const media = (patch: Partial<MediaAsset> = {}): MediaAsset => ({
  id: 'm1',
  garment_id: 'g1',
  category: 'front',
  status: 'pending',
  error_code: null,
  original_filename: 'a.jpg',
  content_type: null,
  size_bytes: null,
  sha256: null,
  width: null,
  height: null,
  created_at: '2026-11-16T10:00:00Z',
  completed_at: null,
  thumbnail_url: null,
  preview_url: null,
  original_url: null,
  ...patch,
});

type Meta = { category: MediaAsset['category'] };
type Deps = UploadDeps<Meta, MediaAsset>;

const ticket = (patch: Partial<MediaAsset> = {}, withUpload = true): UploadTicket<MediaAsset> => ({
  record: media(patch),
  upload: withUpload
    ? {
        url: 'https://storage.test/uploads/m1?sig',
        method: 'PUT',
        headers: { 'Content-Type': 'image/jpeg' },
        expires_at: '2026-11-16T10:15:00Z',
      }
    : null,
});

function setup(overrides: Partial<Deps> = {}, outcomes: UploadOutcome[] = [{ ok: true }]) {
  let id = 0;
  const finished: MediaAsset[] = [];
  const put = vi.fn(() => Promise.resolve(outcomes.shift() ?? ({ ok: true } as const)));
  const requestUpload = vi.fn<Deps['requestUpload']>(() => Promise.resolve(ticket()));
  const complete = vi.fn<Deps['complete']>(() => Promise.resolve(media({ status: 'ready' })));
  const hash = vi.fn(() => Promise.resolve('a'.repeat(64)));
  const deps: Deps = {
    requestUpload,
    complete,
    transport: { put },
    hash,
    contentType: () => 'image/jpeg',
    onFinished: (m) => finished.push(m),
    sleep: () => Promise.resolve(),
    newId: () => `id-${++id}`,
    ...overrides,
  };
  const queue = new UploadQueue<Meta, MediaAsset>(deps, { concurrency: 2, backoffMs: [0, 0, 0] });
  return { queue, put, finished, requestUpload, complete, hash };
}

const file = (name = 'IMG_1.HEIC') => new File([new Uint8Array([1, 2, 3])], name);
const settle = () => vi.waitFor(() => undefined);

async function until(check: () => boolean) {
  await vi.waitFor(() => {
    if (!check()) throw new Error('not yet');
  });
}

describe('UploadQueue', () => {
  it('registers, uploads to storage and completes each photo with a stable key', async () => {
    const { queue, put, finished, requestUpload, complete } = setup();
    queue.add([file()], { category: 'defect' });
    await until(() => finished.length === 1);

    expect(requestUpload).toHaveBeenCalledWith(
      {
        client_upload_id: 'id-1',
        content_type: 'image/jpeg',
        size_bytes: 3,
        sha256: 'a'.repeat(64),
        filename: 'IMG_1.HEIC',
      },
      { category: 'defect' },
    );
    expect(put).toHaveBeenCalledOnce();
    expect(complete).toHaveBeenCalledWith('m1');
    expect(queue.getSnapshot()).toEqual([]);
  });

  it('retries transient failures automatically with the same idempotency key', async () => {
    const { queue, requestUpload, hash, finished } = setup({}, [
      { ok: false, kind: 'network', status: 0 },
      { ok: true },
    ]);
    queue.add([file()], { category: 'front' });
    await until(() => finished.length === 1);
    const keys = requestUpload.mock.calls.map(([body]) => body.client_upload_id);
    expect(keys).toEqual(['id-1', 'id-1']);
    expect(hash).toHaveBeenCalledOnce(); // hash is reused across attempts
  });

  it('asks for a fresh URL when the presigned one expired', async () => {
    const { queue, requestUpload, put, finished } = setup({}, [
      { ok: false, kind: 'expired', status: 403 },
      { ok: true },
    ]);
    queue.add([file()], { category: 'front' });
    await until(() => finished.length === 1);
    expect(requestUpload).toHaveBeenCalledTimes(2);
    expect(put).toHaveBeenCalledTimes(2);
  });

  it('offers manual retry after automatic retries are exhausted', async () => {
    const network: UploadOutcome = { ok: false, kind: 'network', status: 0 };
    const { queue, finished } = setup({}, [network, network, network, network]);
    queue.add([file()], { category: 'front' });
    await until(() => queue.getSnapshot()[0]?.phase === 'failed');
    const [item] = queue.getSnapshot();
    expect(item).toMatchObject({ errorCode: 'network_error', retryable: true });

    queue.retry(item!.id);
    await until(() => finished.length === 1);
  });

  it('does not retry permanent errors', async () => {
    const failing = vi.fn(() => Promise.reject(new ApiError('unsupported_media_type', 415)));
    const { queue } = setup({ requestUpload: failing });
    queue.add([file('clip.mov')], { category: 'front' });
    await until(() => queue.getSnapshot()[0]?.phase === 'failed');
    expect(queue.getSnapshot()[0]).toMatchObject({
      errorCode: 'unsupported_media_type',
      retryable: false,
    });
    expect(failing).toHaveBeenCalledOnce();

    queue.remove(queue.getSnapshot()[0]!.id);
    expect(queue.getSnapshot()).toEqual([]);
  });

  it('hands rejected photos to the server-side list instead of keeping them locally', async () => {
    const rejected = media({ status: 'rejected', error_code: 'invalid_image' });
    const { queue, finished } = setup({ complete: () => Promise.resolve(rejected) });
    queue.add([file()], { category: 'front' });
    await until(() => finished.length === 1);
    expect(finished[0]).toBe(rejected);
    expect(queue.getSnapshot()).toEqual([]);
  });

  it('skips the upload when an earlier attempt already finished the photo', async () => {
    const { queue, put, finished } = setup({
      requestUpload: () => Promise.resolve(ticket({ status: 'ready' }, false)),
    });
    queue.add([file()], { category: 'front' });
    await until(() => finished.length === 1);
    expect(put).not.toHaveBeenCalled();
  });

  it('limits concurrency', async () => {
    let release: () => void = () => undefined;
    const gate = new Promise<void>((resolve) => (release = resolve));
    const put = vi.fn(() => gate.then(() => ({ ok: true }) as const));
    const { queue, finished } = setup({ transport: { put } });
    queue.add([file('1.jpg'), file('2.jpg'), file('3.jpg')], { category: 'detail' });
    await until(() => put.mock.calls.length === 2);
    await settle();
    expect(put).toHaveBeenCalledTimes(2);
    expect(queue.getSnapshot().map((i) => i.phase)).toEqual(['uploading', 'uploading', 'queued']);
    release();
    await until(() => finished.length === 3);
  });
});

describe('UploadQueue: uncategorized photos and resumable items', () => {
  it('uploads photos without a category', async () => {
    const { queue, requestUpload, finished } = setup();
    queue.add([file('1.jpg'), file('2.jpg')], { category: null });
    await until(() => finished.length === 2);
    expect(requestUpload.mock.calls.map(([, meta]) => meta)).toEqual([
      { category: null },
      { category: null },
    ]);
  });

  it('resumes with a known key and keeps held items until the expert saves them', async () => {
    const removed: string[] = [];
    const { queue, requestUpload, finished } = setup({
      onRemoved: (item) => removed.push(item.clientUploadId),
    });
    queue.add([file('a.m4a')], { category: null }, { clientUploadId: 'draft-1', held: true });
    queue.add([file('a.m4a')], { category: null }, { clientUploadId: 'draft-1', held: true });
    await settle();
    expect(queue.getSnapshot()).toHaveLength(1); // same key is not queued twice
    expect(queue.getSnapshot()[0]).toMatchObject({ phase: 'failed', errorCode: 'not_saved' });
    expect(requestUpload).not.toHaveBeenCalled();

    queue.retry(queue.getSnapshot()[0]!.id);
    await until(() => finished.length === 1);
    expect(requestUpload.mock.calls[0]?.[0].client_upload_id).toBe('draft-1');

    queue.add([file('b.m4a')], { category: null }, { clientUploadId: 'draft-2', held: true });
    queue.remove(queue.getSnapshot()[0]!.id);
    expect(removed).toEqual(['draft-2']);
  });
});

describe('declaredContentType', () => {
  it.each([
    [{ name: 'a.jpg', type: 'image/jpeg' }, 'image/jpeg'],
    [{ name: 'a.jpg', type: 'image/jpg' }, 'image/jpeg'],
    [{ name: 'IMG_0001.HEIC', type: '' }, 'image/heic'],
    [{ name: 'scan.heif', type: '' }, 'image/heif'],
    [{ name: 'noext', type: '' }, 'application/octet-stream'],
  ])('%o -> %s', (input, expected) => {
    expect(declaredContentType(input)).toBe(expected);
  });
});
