/**
 * Photo platform adapters (ARCHITECTURE.md §9): hashing, MIME normalization, upload transport.
 * Browser implementations; a native shell can replace them without touching feature code.
 */

const TYPE_BY_EXTENSION: Record<string, string> = {
  jpg: 'image/jpeg',
  jpeg: 'image/jpeg',
  png: 'image/png',
  heic: 'image/heic',
  heif: 'image/heif',
};

/**
 * MIME type to declare for a picked file. Browsers sometimes report HEIC files with an
 * empty type; fall back to the extension. The server detects the real type from the bytes.
 */
export function declaredContentType(file: Pick<File, 'name' | 'type'>): string {
  const type = file.type.toLowerCase();
  if (type === 'image/jpg') return 'image/jpeg';
  if (type) return type;
  const extension = file.name.split('.').pop()?.toLowerCase() ?? '';
  return TYPE_BY_EXTENSION[extension] ?? 'application/octet-stream';
}

/** Lowercase hex SHA-256 of a file (WebCrypto; requires a secure context: HTTPS or localhost). */
export async function sha256Hex(file: Blob): Promise<string> {
  const digest = await crypto.subtle.digest('SHA-256', await file.arrayBuffer());
  return Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, '0')).join('');
}

export type UploadOutcome =
  { ok: true } | { ok: false; kind: 'network' | 'expired' | 'rejected'; status: number };

export interface UploadTransport {
  put(
    request: { url: string; headers: Record<string, string>; body: Blob },
    onProgress: (fraction: number) => void,
    signal?: AbortSignal,
  ): Promise<UploadOutcome>;
}

/**
 * Direct PUT to object storage with progress (fetch cannot report upload progress).
 * The storage origin is different from the app origin: no cookies are sent (ADR-0006).
 */
export const xhrUploadTransport: UploadTransport = {
  put({ url, headers, body }, onProgress, signal) {
    return new Promise((resolve) => {
      const xhr = new XMLHttpRequest();
      xhr.open('PUT', url);
      xhr.withCredentials = false;
      for (const [name, value] of Object.entries(headers)) xhr.setRequestHeader(name, value);
      xhr.upload.onprogress = (event) => {
        if (event.lengthComputable) onProgress(event.loaded / event.total);
      };
      xhr.onload = () => {
        if (xhr.status >= 200 && xhr.status < 300) resolve({ ok: true });
        // 403 from S3 on a presigned URL means expired (or otherwise no longer valid).
        else if (xhr.status === 403) resolve({ ok: false, kind: 'expired', status: 403 });
        else if (xhr.status >= 500) resolve({ ok: false, kind: 'network', status: xhr.status });
        else resolve({ ok: false, kind: 'rejected', status: xhr.status });
      };
      xhr.onerror = () => resolve({ ok: false, kind: 'network', status: 0 });
      xhr.ontimeout = xhr.onerror;
      xhr.onabort = xhr.onerror;
      signal?.addEventListener('abort', () => xhr.abort());
      xhr.send(body);
    });
  },
};
