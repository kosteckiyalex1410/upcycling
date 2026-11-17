# Security and operational follow-ups

Known gaps after Slice 1. None blocks local development or the expert MVP slices; items marked
**before production** must be resolved before real expert data or a public deployment.
Convert items into GitHub issues when they are scheduled.

## Before production

| # | Area | Task | Why |
|---|---|---|---|
| F1 | Email | Choose the production SMTP provider (ADR needed); configure SPF/DKIM/DMARC for the sender domain | Login depends on deliverability; production config already refuses to start without explicit SMTP host/sender and TLS |
| F2 | Hosting | Choose hosting and reverse proxy (open decision 1) honouring ADR-0005; set `UPCYCLING_FORWARDED_ALLOW_IPS` to the proxy address only | Per-IP rate limits and logs rely on correct client IPs |
| F3 | Headers | Serve the PWA with a strict Content-Security-Policy (`connect-src` must include the storage origin for uploads, ADR-0006), `Strict-Transport-Security`, `Referrer-Policy: no-referrer`, `Permissions-Policy` (allow `camera` for self) | API responses already send `nosniff`, `no-referrer`, `DENY`, `no-store`; the static host is not configured yet |
| F4 | Secrets | Store `UPCYCLING_SECRET_KEY`, database and SMTP credentials in the platform secret manager; document rotation (rotating the key invalidates pending login codes and resets rate-limit digests, not sessions) | Secrets are environment-only; rotation procedure is undocumented |
| F5 | Data | Backups and restore test for PostgreSQL; define retention/deletion (open decision 5) | Required by ARCHITECTURE.md §10 before external users |
| F6 | Real device | Manual iPhone Safari + installed-PWA verification of sign-in (link and code), install, update prompt, safe areas, and the Slice 1 photo checklist in `docs/development.md` (camera, library multi-select, HEIC kept or converted, interrupted uploads) | Only WebKit emulation has been tested |
| F20 | Storage | Choose the production S3-compatible provider with hosting (open decision 1); verify it enforces signed `Content-Length` and `x-amz-checksum-sha256` on presigned PUTs; private bucket, bucket-scoped credential, CORS rule, versioning off/purge rules; EU region if data residency is required | ADR-0006 provider requirements |
| F21 | Privacy | Confirm the policy for location (GPS) metadata in originals, retention and training consent (open decision 5); adopt or amend the proposed export default in ADR-0006 (no original bytes, no metadata, no location, no filenames, pseudonymous owners) before Slice 6 | Originals keep EXIF/GPS and are owner-only; display copies carry no metadata (verified 2026-11-16) |
| F22 | Operations | Run `storage-sweep` daily as a periodic job of the Slice 2 worker (single run at a time, outcome logged); alert on `garment_purge_deferred`, `media_purge_deferred`, `media_object_missing`, `storage_unavailable`. If any deployment exists before Slice 2, schedule `python -m app.cli storage-sweep` daily with that host's cron | Deferred deliberately: no deployment exists, hosting is undecided (open decision 1) and a host-level scheduler would be thrown away once the worker exists; without a sweep only failed deletions and abandoned uploads accumulate |

## Hardening (schedule within the next slices)

| # | Area | Task | Why |
|---|---|---|---|
| F7 | Auth data | Periodic job to delete expired/consumed `login_challenges` (e.g. older than the rate-limit window + 1 day) and expired/revoked `auth_sessions` | Tables grow without bound; also minimizes retained data. Natural fit once the Slice 2 worker exists |
| F8 | Sessions | Add an idle timeout and/or sliding renewal (currently absolute 30 days); record `last_seen_at` | Limits the value of a stolen cookie |
| F9 | Sessions | Session list in Settings ("signed-in devices") with per-session revocation | Today only "sign out" and "sign out everywhere" exist |
| F10 | Rate limiting | Add a limit on verification attempts per IP across challenges, and per-user/IP rate limits on authenticated write endpoints (garment creation, upload tickets; today only count caps apply: 40 photos/garment, 20 unfinished uploads/user) | Code guessing is limited per challenge (5) and by login-request limits, not per IP globally |
| F11 | Auth | Passkeys as an additional login method (ADR-0003 extension point) | Stronger than email possession |
| F12 | Timing | Make `POST /auth/login-requests` timing independent of whether the email exists (constant work or fixed minimum latency) | Small residual enumeration signal; responses are already identical |
| F13 | API contract | Make the OpenAPI breaking-change check (`oasdiff`) a blocking CI gate once `main` has a baseline | Planned in ADR-0004 |
| F14 | Supply chain | Pin GitHub Actions to commit SHAs; enable Dependabot/Renovate for uv, pnpm, Docker and Actions; enable GitHub secret scanning and push protection | Actions are pinned to major tags only |
| F15 | Supply chain | `deepmerge` ≤ 4.3.1 (low, prototype poisoning) remains via `workbox-build`, build-time only, no patched release; remove when upstream updates. `glob`/`minimatch` are forced to patched versions via `pnpm-workspace.yaml` overrides — drop the overrides when upstream ranges include fixes | Full-tree audit gate is set to moderate+ because of this |
| F16 | Observability | Structured metrics and alerting for login failures, rate-limit hits, email send failures (`login_email_send_failed`), 5xx rates | Logs exist; nothing alerts yet |
| F17 | Container | Image vulnerability scan in CI (e.g. Trivy/Grype); read-only root filesystem and dropped capabilities in the deployment manifest | Image is non-root and minimal but unscanned |
| F18 | Tooling | Upgrade uv (pinned 0.9.26; current 0.13.x) and TypeScript 7 when `typescript-eslint` and `openapi-typescript` support it | Keep toolchain current |
| F19 | Branding | Replace placeholder PWA icons | Cosmetic |
| F23 | Media | Move image verification/preview rendering to the Slice 2 job worker (and a separate process) if `complete` latency or decoder risk warrants it; consider a bucket lifecycle rule expiring `uploads/` after 1 day | Decoding untrusted HEIC/JPEG runs in the API process (size and pixel caps apply) |
| F24 | Readiness | Include storage reachability in `/health/ready`, or a separate storage health metric | Readiness covers PostgreSQL only; storage outages surface as `storage_unavailable` (503) |
| F25 | Uploads | Persist unsent photos locally (IndexedDB) only if open decision 4 requires offline capture; today the upload queue lives in memory and photos must be re-selected after iOS discards the page | CLAUDE.md §7: best effort only |
| F26 | Media | Convert display copies (and future exports) from the embedded ICC profile (e.g. iPhone Display P3) to sRGB before dropping the profile | Today the profile is dropped without conversion, so wide-gamut colours look slightly duller in previews — relevant for fabric colour judgement |
| F27 | Voice | Verify voice recording on a real iPhone (Safari and installed PWA: permission prompts, MP4 output, screen lock, calls, IndexedDB retention) and record results in the PR; add `voice_note_transcripts` (machine/expert, provenance) with the Slice 2+ speech adapter | Automated tests use WebKit/Chromium fake microphones only (ADR-0007) |
| F28 | Media | Re-test the audio parser against recordings from new iOS/Chrome versions (keep fixtures in `backend/tests/fixtures/audio`); consider PyAV behind `probe_audio` if unusual but valid files are rejected | In-house MP4/WebM parser (ADR-0007) |
