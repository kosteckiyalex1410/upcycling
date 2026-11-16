# Security and operational follow-ups

Known gaps after Slice 0. None blocks local development or the expert MVP slices; items marked
**before production** must be resolved before real expert data or a public deployment.
Convert items into GitHub issues when they are scheduled.

## Before production

| # | Area | Task | Why |
|---|---|---|---|
| F1 | Email | Choose the production SMTP provider (ADR needed); configure SPF/DKIM/DMARC for the sender domain | Login depends on deliverability; production config already refuses to start without explicit SMTP host/sender and TLS |
| F2 | Hosting | Choose hosting and reverse proxy (open decision 1) honouring ADR-0005; set `UPCYCLING_FORWARDED_ALLOW_IPS` to the proxy address only | Per-IP rate limits and logs rely on correct client IPs |
| F3 | Headers | Serve the PWA with a strict Content-Security-Policy, `Strict-Transport-Security`, `Referrer-Policy: no-referrer`, `Permissions-Policy` | API responses already send `nosniff`, `no-referrer`, `DENY`, `no-store`; the static host is not configured yet |
| F4 | Secrets | Store `UPCYCLING_SECRET_KEY`, database and SMTP credentials in the platform secret manager; document rotation (rotating the key invalidates pending login codes and resets rate-limit digests, not sessions) | Secrets are environment-only; rotation procedure is undocumented |
| F5 | Data | Backups and restore test for PostgreSQL; define retention/deletion (open decision 5) | Required by ARCHITECTURE.md §10 before external users |
| F6 | Real device | Manual iPhone Safari + installed-PWA verification of sign-in (link and code), install, update prompt, safe areas | Only WebKit emulation has been tested |

## Hardening (schedule within the next slices)

| # | Area | Task | Why |
|---|---|---|---|
| F7 | Auth data | Periodic job to delete expired/consumed `login_challenges` (e.g. older than the rate-limit window + 1 day) and expired/revoked `auth_sessions` | Tables grow without bound; also minimizes retained data. Natural fit once the Slice 2 worker exists |
| F8 | Sessions | Add an idle timeout and/or sliding renewal (currently absolute 30 days); record `last_seen_at` | Limits the value of a stolen cookie |
| F9 | Sessions | Session list in Settings ("signed-in devices") with per-session revocation | Today only "sign out" and "sign out everywhere" exist |
| F10 | Rate limiting | Add a limit on verification attempts per IP across challenges, and per-IP limits on authenticated write endpoints as they are added | Code guessing is limited per challenge (5) and by login-request limits, not per IP globally |
| F11 | Auth | Passkeys as an additional login method (ADR-0003 extension point) | Stronger than email possession |
| F12 | Timing | Make `POST /auth/login-requests` timing independent of whether the email exists (constant work or fixed minimum latency) | Small residual enumeration signal; responses are already identical |
| F13 | API contract | Make the OpenAPI breaking-change check (`oasdiff`) a blocking CI gate once `main` has a baseline | Planned in ADR-0004 |
| F14 | Supply chain | Pin GitHub Actions to commit SHAs; enable Dependabot/Renovate for uv, pnpm, Docker and Actions; enable GitHub secret scanning and push protection | Actions are pinned to major tags only |
| F15 | Supply chain | `deepmerge` ≤ 4.3.1 (low, prototype poisoning) remains via `workbox-build`, build-time only, no patched release; remove when upstream updates. `glob`/`minimatch` are forced to patched versions via `pnpm-workspace.yaml` overrides — drop the overrides when upstream ranges include fixes | Full-tree audit gate is set to moderate+ because of this |
| F16 | Observability | Structured metrics and alerting for login failures, rate-limit hits, email send failures (`login_email_send_failed`), 5xx rates | Logs exist; nothing alerts yet |
| F17 | Container | Image vulnerability scan in CI (e.g. Trivy/Grype); read-only root filesystem and dropped capabilities in the deployment manifest | Image is non-root and minimal but unscanned |
| F18 | Tooling | Upgrade uv (pinned 0.9.26; current 0.13.x) and TypeScript 7 when `typescript-eslint` and `openapi-typescript` support it | Keep toolchain current |
| F19 | Branding | Replace placeholder PWA icons | Cosmetic |
