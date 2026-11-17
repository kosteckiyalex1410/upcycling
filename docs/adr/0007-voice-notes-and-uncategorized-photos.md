# ADR-0007: Voice notes and uncategorized photos (Slice 1.1)

- **Status:** accepted
- **Date:** 2026-11-17
- **Deciders:** product owner (data model and audio verification approach approved 2026-11-17), Claude Code (author)
- **Related:** ADR-0006 (storage and upload protocol), `ARCHITECTURE.md` §5–§7, open decision 3 (speech provider), open decision 5 (retention and consent)

## Context and problem

Real-world use is a stylist in a secondhand shop holding garments with one hand. Slice 1 asked for a category before every photo and offered only typed notes. Slice 1.1 makes capture camera-first and adds spoken observations. We need to decide:

- whether a photo must have a category;
- how voice recordings are stored and related to future transcripts (Slice 2+), without redesigning storage later;
- how the server verifies that an upload is really a complete, supported recording of acceptable length;
- how recordings survive iOS interrupting or discarding the web app.

## Considered options

**Data model for recordings**

1. **Separate `voice_notes` table** (chosen). Own columns (codec, duration, recorded time) and constraints; future transcripts are separate rows pointing at a voice note.
2. `media_assets.kind = 'image' | 'audio'` (the sketch in `ARCHITECTURE.md` v0.3). One table for all media, but image-only columns and the `ready` constraint (dimensions, preview, thumbnail) would become conditional on `kind`, and every photo query would need a `kind` filter.

**Server-side audio verification**

1. **Small in-house parser** (chosen) for the two containers browsers record: MP4 (Safari/iOS: fragmented MP4 with AAC) and WebM (Chrome: Opus, often without a duration header). It checks the container end to end, exactly one audio track and no video, codec AAC or Opus, and the real duration from sample/block timing.
2. PyAV (bundled FFmpeg). Most robust for unusual files, but adds ~45 MB of native libraries to the API image, FFmpeg parses untrusted input in the API process, and the wheel's build flags list GPL encoders although it reports LGPL, so licensing would need review.

**Category**: required (Slice 1) vs. **optional** (chosen).

## Decision

### Photos

- `media_assets.category` is nullable. New uploads default to no category; the expert can assign, change or remove it later (`PATCH /media/{id}` with `{"category": null}` removes it). Existing photos keep their category. The category values themselves are unchanged and stay stable API codes.
- The PWA shows one gallery with category labels on thumbnails; capture actions (camera, library, voice) sit in a bar at the bottom edge of the screen.

### Voice notes

- Table `voice_notes`: id, garment, owner, `client_upload_id`, status (`pending` → `ready` | `rejected`), `error_code`, declared type/size/SHA-256/duration, `recorded_at` (device time), and the verified `content_type`, `codec`, `size_bytes`, `sha256`, `duration_ms`, `audio_key`. Database CHECKs make `ready` impossible without verified content and restrict the container to `audio/mp4` or `audio/webm`.
- **Same upload protocol as photos (ADR-0006):** `POST /garments/{id}/voice-notes/uploads` (idempotent, presigned PUT bound to type, length and SHA-256, 15 min), browser PUT to storage, `POST /garments/{id}/voice-notes/complete` (verification). The original is stored byte-for-byte at `voice-notes/{garment}/{voice_note}`, written only by the server.
- **Verification:** size and SHA-256 match the declaration; the parser above identifies the container from the bytes (must match the declared one), requires one AAC or Opus audio track, rejects truncated files (`invalid_audio`), and measures duration from the samples (limit 5 min + 2 s encoder tolerance, `audio_too_long`). It does not decode the audio payload.
- **Playback:** `GET /voice-notes/{id}/audio`, authenticated and owner-only, `Cache-Control: private, no-cache`, ETag, and a single HTTP byte range (`206`), which Safari requires for `<audio>`. No storage URL is exposed for reading.
- **Deletion:** permanent for the row and the audio, like photos; deleting a garment deletes its voice notes. `storage-sweep` also removes deleted, stale (pending/rejected > 24 h) and orphaned recordings under `voice-notes/`.
- **Limits** (configurable): 20 MB and 5 minutes per recording, 20 voice notes per garment; unfinished uploads count towards the existing per-user limit.
- **Browser recording:** `MediaRecorder` with feature detection. We request `audio/mp4;codecs=mp4a.40.2`, then `audio/mp4`, `audio/webm;codecs=opus`, `audio/webm`, and trust only `recorder.mimeType`. The recorder stops at the limit (warning 30 s before), and stops and keeps what was captured when the page is hidden (backgrounding, screen lock), the microphone track ends, or the system stops the recorder (e.g. a phone call). The microphone is released after every recording.
- **Not losing recordings:** a finished recording is copied to IndexedDB at once (best effort, as allowed by CLAUDE.md §7) and removed when the server has finished it or the expert discards it. Copies found when a garment is opened are shown as "not saved" with Save/Delete. This does not make the app offline-capable (open decision 4 remains open).

### Future transcripts (not implemented)

Transcripts will be **separate records referencing `voice_notes.id`**, never columns that overwrite each other: one table (e.g. `voice_note_transcripts`) with `source` (`machine` | `expert`), text, language, provider/model/prompt provenance for machine output, the expert who corrected it, `supersedes_id`, and timestamps. The audio is never replaced or re-encoded in place. Speech provider choice remains open decision 3.

## Consequences

- Photo and voice upload code share the protocol, the client upload queue and the storage sweep; the server-side services stay separate and simple.
- Clients must treat `MediaAsset.category` as nullable (an API change within `/api/v1`; the generated PWA client is the only consumer, so no external migration is needed).
- The parser is ~400 lines of security-relevant code that must be maintained. It is tested against real WebKit and Chromium recordings, non-fragmented M4A, video files, other codecs, WAV, truncated files and malformed input. Recordings from other sources (e.g. voice memos converted by iOS) are accepted only if they are MP4/AAC or WebM/Opus.
- Downgrading migration `0003` refuses to run while voice notes or uncategorized photos exist, so a rollback cannot silently drop recordings or invent categories.
- **Not verified on a real iPhone yet:** microphone permission prompts in Safari and the installed PWA, MediaRecorder output on the target iOS version, behaviour on screen lock and phone calls, and IndexedDB retention. These are on the manual checklist in `docs/development.md`.
- **Reversibility:** high for limits and accepted formats (configuration/parser); moderate for the parser (PyAV could replace it behind `probe_audio` without API changes); low for the table split (a migration would be needed to merge media tables).
