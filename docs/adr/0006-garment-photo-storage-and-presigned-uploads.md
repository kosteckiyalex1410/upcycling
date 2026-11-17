# ADR-0006: Garment photo storage, presigned uploads and media access

- **Status:** accepted
- **Date:** 2026-11-16
- **Deciders:** product owner (Slice 1 decisions), Claude Code (author)
- **Related:** ADR-0003 (sessions, CSRF), ADR-0005 (same-origin topology), ADR-0007 (voice notes, optional photo category), `ARCHITECTURE.md` §5–§6, §12 open decisions 1 and 5
- **Amended:** 2026-11-17 by ADR-0007 — the photo category is optional; the same protocol and sweep also cover voice recordings.

## Context and problem

Slice 1 lets the expert photograph garments on an iPhone and keep the **original** photos as evidence for later analysis and model evaluation. Photos are large (2–15 MB HEIC/JPEG), arrive over mobile networks that drop, and must stay private. We need to decide:

- where bytes live and how they get there;
- how the server knows an uploaded object is what the client claimed and is really an image;
- how the PWA displays photos, including HEIC in browsers that cannot decode it;
- what "delete" means while retention policy (open decision 5) is undecided.

The production storage provider is **not** chosen (open decision 1); everything below must work with any S3-compatible provider.

## Considered options

**Upload path**

1. **Presigned PUT directly from the browser to object storage** (chosen). Bytes bypass the API; requires CORS on the bucket for the PWA origin.
2. Upload through the API (`PUT /api/v1/uploads/{id}`), API streams to storage. Same-origin, no bucket CORS, but every byte passes through the API process.
3. Same-origin reverse-proxy path (`/storage/*`) to the provider. Breaks SigV4 signatures unless the proxy preserves the provider's `Host`; provider-specific.
4. Presigned POST with a policy (`content-length-range`). Enforces a size *range* but not the exact checksum, and provider support varies more than for PUT.

**Reading photos**

- Short-lived presigned GET URLs per image vs. **authenticated, same-origin API endpoints** (chosen).

**HEIC display**

- Client-side decoding (WASM libheif, large bundle) vs. **server-rendered JPEG previews** (chosen).

## Decision

### Upload protocol (all steps idempotent)

1. `POST /api/v1/garments/{id}/media/uploads` with `client_upload_id` (idempotency key), optional category, declared type, size and SHA-256 (computed in the browser with WebCrypto). The server checks ownership, the declared type (JPEG, PNG, HEIC/HEIF) and the size limit, creates a `pending` row, and returns a presigned **PUT** for `uploads/{media_id}`. Calling again with the same key returns the same photo with a fresh URL (e.g. after expiry); a different payload under the same key is `409 idempotency_conflict`.
2. The browser PUTs the bytes to storage. The signature covers **`Content-Type`, `Content-Length` and `x-amz-checksum-sha256`**: storage rejects a different type, a different length or different bytes. URLs expire after 15 minutes (`UPCYCLING_UPLOAD_URL_TTL_SECONDS`). The request is cross-origin and carries **no cookies**.
3. `POST /api/v1/garments/{id}/media/complete` with `media_id`. The server re-reads the staging object (capped at the size limit), recomputes size and SHA-256, detects the real type from magic bytes, fully decodes the image (Pillow + `pi-heif`), and checks the pixel limit. On success it writes the verified bytes to `originals/{garment_id}/{media_id}` (never re-encoded), renders a 1600 px preview and a 400 px thumbnail (JPEG, orientation applied, **all metadata stripped**), marks the photo `ready`, and deletes the staging object. On failure the photo becomes `rejected` with a stable `error_code` and its bytes are deleted. `409 upload_incomplete` means "bytes not there yet, retry".

The final status change is a compare-and-set from `pending`, so concurrent completes cannot produce two outcomes. Originals are written **only by the server**, under keys never handed to a client: a leaked or replayed upload URL can only touch the staging key. A database CHECK makes `ready` impossible without verified content fields.

### Storage layout and access

- Keys contain UUIDs only: `uploads/{media}`, `originals/{garment}/{media}`, `derived/{garment}/{media}/{preview|thumbnail}.jpg`.
- Bucket is private. Credentials stay on the server (`UPCYCLING_STORAGE_*`). Production refuses to start with development storage credentials or non-HTTPS storage endpoints.
- **Bucket CORS** allows only `PUT` from the PWA origin(s) (`UPCYCLING_PUBLIC_ORIGIN` + `UPCYCLING_EXTRA_ALLOWED_ORIGINS`), only the headers `content-type` and `x-amz-checksum-sha256`; `python -m app.cli storage-init` applies it. The **API keeps CORS disabled**; cookies, the `__Host-` session cookie and the Origin check (ADR-0003) are unchanged.
- **Reads go through the API**: `GET /api/v1/media/{id}/thumbnail|preview|original`, authenticated and owner-checked on every request; `Cache-Control: private, no-cache` with an `ETag` (cheap `304` revalidation that still re-checks the session), `nosniff`, `Content-Security-Policy: default-src 'none'; sandbox`, `Cross-Origin-Resource-Policy: same-origin`; originals are served as attachments with the **detected** type. No storage URL is ever exposed for reading. This deliberately deviates from "signed download URLs" in `ARCHITECTURE.md` §3: access is revoked instantly on sign-out and there is no second origin for images. Revisit if bandwidth through the API becomes a cost or latency problem.
- Another user's garment or photo is `404 not_found`, indistinguishable from a missing one.

### Formats and metadata

- Accepted: JPEG, PNG, HEIC/HEIF (HEVC still images). AVIF, GIF, SVG, video and anything whose magic bytes and decoded format disagree are rejected (`unsupported_media_type`/`invalid_image`).
- Originals are kept byte-for-byte, **including EXIF/GPS**, visible only to the owner. Previews and thumbnails carry no metadata. Width/height are stored as displayed (orientation applied); the raw EXIF orientation is stored for future annotation geometry.
- Review 2026-11-16: originals contain whatever the camera wrote — EXIF with GPS coordinates, capture time, device make/model (sometimes serial numbers), XMP, maker notes and comments. None of it is parsed into the database except the orientation tag; the client-supplied `original_filename` is stored as given. Display copies are rendered from decoded pixels with the image's `info` cleared, so no EXIF, GPS, XMP, ICC profile or JPEG comment is carried over (a JPEG comment previously was; fixed and covered by `test_display_copies_carry_no_metadata_of_any_kind`). Nothing is logged.
- `pi-heif` 1.4 (Python bindings BSD-3-Clause; bundled `libheif` and `libde265` are LGPL-3.0 shared libraries, decode-only, no x265/GPL encoder).

### Privacy-safe default for future dataset exports (proposed; confirm with open decision 5 before Slice 6)

Until a recorded decision says otherwise, a dataset export (Slice 6) must:

1. **Never contain original bytes.** Export images are produced from decoded pixels (orientation applied), like display copies, with **no metadata of any kind**: no EXIF (GPS, timestamps, device make/model/serial, lens, software), XMP, IPTC, maker notes, embedded thumbnails or comments. Colours are converted to sRGB before any ICC profile is dropped. The encoding (lossless or quality setting) is recorded per export.
2. **Contain no location in any form**, including values derived from GPS (city, country). Exporting location requires an explicit, recorded decision and consent.
3. **Omit `original_filename`, owner email and other account data.** Owners appear as export-specific pseudonymous IDs; the mapping stays in the database.
4. **Coarsen time** to what an experiment needs (e.g. capture month for time-based splits), never exact capture timestamps from EXIF.
5. **Record provenance in the immutable manifest:** the metadata policy version, media IDs, the SHA-256 of the original and of the exported file, and the export code version. An automated check fails the export if any exported file contains EXIF, XMP, ICC or comment data.

Photos may also show people wearing garments, labels with names, or backgrounds; consent and redaction for image *content* are part of open decision 5 and are not solved by metadata stripping.

### Deletion (until retention policy is decided)

- Deleting a photo or garment is **permanent**: rows and all objects. The resource disappears from the API immediately (`deleted_at`), storage objects are deleted in the same request, and rows are removed afterwards. If storage fails, the rows stay marked and `python -m app.cli storage-sweep` finishes the job.
- The sweep also removes unfinished uploads and rejected photos older than 24 h (`UPCYCLING_STALE_UPLOAD_SECONDS`), stray staging objects, and objects under `originals/`/`derived/` older than one hour that no row references. It will be scheduled by the Slice 2 worker; until then it is an operator command.

### Limits (configurable)

30 MB per file, 100 megapixels, 40 photos per garment (pending + ready), 20 unfinished uploads per user.

### Local development and CI

SeaweedFS 4.52 (`chrislusf/seaweedfs`, Apache-2.0) in `compose.yaml` and CI (`scripts/start-ci-storage.sh`); backend tests run against it (no storage fake). Adapter: boto3 (`S3ObjectStorage`) behind the `ObjectStorage` port. Probe results that motivated the protocol: SeaweedFS enforces bucket CORS per origin and rejects PUTs whose type, length or checksum differ from the signature.

## Consequences

- Upload bandwidth bypasses the API; downloads (mostly small thumbnails) pass through it.
- Each environment needs: an HTTPS storage endpoint reachable from the expert's iPhone (`UPCYCLING_STORAGE_PUBLIC_ENDPOINT_URL` if the backend uses an internal endpoint), a private bucket, a credential scoped to that bucket, and the CORS rule. When the PWA gets a Content-Security-Policy (follow-up F3), `connect-src` must include the storage origin.
- Provider requirements: SigV4 presigned PUT with signed `Content-Length` and `x-amz-checksum-sha256` (documented for AWS S3, verified here for SeaweedFS; must be verified for any other candidate such as Cloudflare R2 before it is chosen), bucket CORS, versioning off or purge rules for deleted objects. The server-side verification still rejects bad bytes if a provider ignores the checksum.
- Verification and preview rendering run inside the `complete` request (about 1 s per 12 MP HEIC). If real usage shows latency problems, move it to the Slice 2 job worker without changing the API (clients already treat `complete` as possibly slow and retryable).
- Image decoders (libheif, Pillow) parse untrusted input in the API process; mitigated by size/pixel caps and dependency audits; isolating decoding in the worker is a follow-up.
- **Reversibility:** high for the provider (endpoint + credentials + CORS), moderate for the read path (API endpoints could start redirecting to signed URLs without a client change because clients use the returned `*_url` fields), low for the key layout (migration needed).
