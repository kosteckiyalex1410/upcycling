/**
 * Local copies of voice recordings that are not yet stored on the server (ADR-0007).
 *
 * Best effort only (CLAUDE.md §7): IndexedDB may be unavailable (private mode), full, or
 * cleared by iOS for an unused web app. Every failure is swallowed; the in-memory flow still
 * works. A draft is removed once the server has finished the upload or the expert discards
 * it. Bytes are stored as ArrayBuffer (more reliable than Blob in older WebKit).
 */

export type VoiceDraft = {
  clientUploadId: string;
  garmentId: string;
  data: ArrayBuffer;
  mimeType: string;
  durationMs: number;
  recordedAt: string;
};

export interface VoiceDraftStore {
  put(draft: VoiceDraft): Promise<void>;
  list(garmentId: string): Promise<VoiceDraft[]>;
  remove(clientUploadId: string): Promise<void>;
}

const DB_NAME = 'upcycling-drafts';
const STORE = 'voice-notes';

function request<T>(req: IDBRequest<T>): Promise<T> {
  return new Promise((resolve, reject) => {
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error ?? new Error('IndexedDB request failed'));
  });
}

function open(): Promise<IDBDatabase> {
  const req = indexedDB.open(DB_NAME, 1);
  req.onupgradeneeded = () => {
    const store = req.result.createObjectStore(STORE, { keyPath: 'clientUploadId' });
    store.createIndex('garmentId', 'garmentId');
  };
  return request(req);
}

async function withStore<T>(
  mode: IDBTransactionMode,
  run: (store: IDBObjectStore) => IDBRequest<T>,
): Promise<T> {
  const db = await open();
  try {
    return await request(run(db.transaction(STORE, mode).objectStore(STORE)));
  } finally {
    db.close();
  }
}

export function indexedDbVoiceDraftStore(): VoiceDraftStore {
  const available = typeof indexedDB !== 'undefined';
  return {
    async put(draft) {
      if (!available) return;
      try {
        await withStore('readwrite', (store) => store.put(draft));
      } catch {
        // best effort
      }
    },
    async list(garmentId) {
      if (!available) return [];
      try {
        const drafts = await withStore('readonly', (store) =>
          store.index('garmentId').getAll(garmentId),
        );
        return drafts as VoiceDraft[];
      } catch {
        return [];
      }
    },
    async remove(clientUploadId) {
      if (!available) return;
      try {
        await withStore('readwrite', (store) => store.delete(clientUploadId));
      } catch {
        // best effort
      }
    },
  };
}

export function memoryVoiceDraftStore(initial: VoiceDraft[] = []): VoiceDraftStore {
  const drafts = new Map(initial.map((d) => [d.clientUploadId, d]));
  return {
    put: (draft) => {
      drafts.set(draft.clientUploadId, draft);
      return Promise.resolve();
    },
    list: (garmentId) =>
      Promise.resolve([...drafts.values()].filter((d) => d.garmentId === garmentId)),
    remove: (id) => {
      drafts.delete(id);
      return Promise.resolve();
    },
  };
}
