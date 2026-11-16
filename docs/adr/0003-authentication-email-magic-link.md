# ADR-0003: Authentication — email magic link with server-side sessions

- **Status:** accepted
- **Date:** 2026-11-12
- **Deciders:** product owner (D1, modified from the passkey proposal), Claude Code (author)
- **Approval note:** the 6-digit one-time code alongside the magic link was explicitly approved by the product owner on 2026-11-12.
- **Resolves:** `ARCHITECTURE.md` §12 open decision 2 (initial identity mechanism)

## Context and problem

The MVP serves one expert designer on iPhone Safari and an installed PWA, but every project/media endpoint must be authenticated and ownership-checked. The mechanism must be secure on iOS, avoid a heavy user-management system, and leave room to add passkeys later.

iOS specifics that shape the design:

- An **installed iOS PWA has its own cookie jar**, separate from Safari. A magic link tapped in Mail opens in Safari, so a session created there is not visible inside the installed PWA.
- Safari blocks **cross-site cookies**, so the API and PWA must be same-site (ADR-0005).
- Corporate mail scanners may **prefetch links**, which can consume single-use tokens.

## Considered options

1. Passkeys (WebAuthn) + CLI invite — strongest, no email provider; deferred by product owner.
2. **Email magic link + server-side session cookie** — familiar, simple, needs SMTP.
3. Managed identity provider (OIDC) — vendor lock-in; redirect flows escape the installed PWA.
4. Email + password — password storage burden, poor mobile UX.

## Decision

Option 2, with the following design:

**Login request** — `POST /api/v1/auth/login-requests {email}` always answers `202` with an opaque `challenge_id`, whether or not the email belongs to a user (no account enumeration). For an active user, one email is sent containing:

- a **magic link** `https://<origin>/auth/verify#token=<token>` — the token is in the URL **fragment**, so it is never sent to servers, proxies or access logs, and link-prefetching scanners that do not run JavaScript cannot consume it; the PWA page posts it to `POST /api/v1/auth/login-requests/verify-token`;
- a **6-digit one-time code** for the installed iOS PWA, entered in-app via `POST /api/v1/auth/login-requests/{challenge_id}/verify-code`. This is a fallback inside the same login request, not a separate mechanism, and is what makes email login work in an installed PWA.

**Tokens** — 256-bit random link token (stored as SHA-256), code stored as HMAC-SHA-256 with the server secret. Both expire after 15 minutes; a challenge is **single-use** (consumed by whichever method is used first); the code allows at most 5 failed attempts.

**Atomicity** — verification locks the challenge row (`SELECT … FOR UPDATE`) and consumes it with a compare-and-set `UPDATE … WHERE consumed_at IS NULL AND expires_at > now AND failed_attempts < max RETURNING id`; only the request whose update returns a row may issue a session. Failed attempts are incremented in SQL (`failed_attempts + 1`). Either mechanism alone prevents reuse; concurrency tests (`tests/integration/test_auth_concurrency.py`) fail when both are removed.

**Sessions** — opaque 256-bit session token in a host-only `HttpOnly`, `SameSite=Lax`, `Secure` (mandatory in production), `Path=/` cookie named `__Host-upcycling_session` (the `__Host-` prefix is used whenever the cookie is `Secure`, so no subdomain can set or shadow it); only its SHA-256 hash is stored in `auth_sessions`. Sessions have an absolute 30-day lifetime and record the login method. **Revocation:** `POST /auth/logout` (current session), `POST /auth/sessions/revoke-all` (all of the user's sessions), and the `revoke-sessions` CLI command.

**Rate limiting** — PostgreSQL-backed (no Redis): login requests are limited per email (5 / 15 min) and per client IP (20 / 15 min), counted from `login_challenges`. Concurrent requests for the same email or IP are serialized with transaction-scoped PostgreSQL advisory locks, so the count-then-insert check cannot be raced. Email and IP are stored only as HMAC digests. Limits are configuration values.

**CSRF** — `SameSite=Lax` plus a server-side `Origin` allowlist check on every state-changing `/api` request; a missing, `null` or foreign `Origin` is rejected with `403 origin_not_allowed`. A test enumerates every state-changing operation in the OpenAPI document, so new endpoints are covered automatically.

**Users** — no sign-up or user administration. The expert account is created with `python -m app.cli create-user`; unknown emails silently receive nothing.

**Email delivery** — an `EmailSender` port with a generic SMTP adapter. Development uses **Mailpit** (Docker Compose). The production email provider is **not yet chosen**; any SMTP-capable provider can be configured without code changes.

**Modularity for passkeys** — session issuance/resolution (`application/auth/sessions.py`) is independent of login methods (`application/auth/email_login.py`). A future passkey method only needs to verify the credential and call `issue_session(..., method=AuthMethod.PASSKEY)`; `auth_sessions.auth_method` already records the method.

## Consequences

- Login depends on email deliverability; the production SMTP provider is an open decision.
- Email is a weaker factor than passkeys; account security equals mailbox security.
- Rate limiting is per-process-consistent because it is DB-backed; IP-based limits require correct proxy-header configuration behind a reverse proxy (`--forwarded-allow-ips`).
- Expired `login_challenges` rows accumulate; a pruning job is needed before data volume matters (tracked as follow-up).
- Native clients (future) would need a bearer-token variant of session resolution; the single `current_user` dependency is the extension point.
- **Reversibility:** high. Adding passkeys is additive; replacing with an OIDC provider changes only the login endpoints and session issuance.
