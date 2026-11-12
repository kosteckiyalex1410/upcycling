# ADR-0005: Same-origin deployment topology

- **Status:** accepted
- **Date:** 2026-11-12
- **Deciders:** product owner (D5), Claude Code (author)
- **Constrains:** `ARCHITECTURE.md` §12 open decision 1 (hosting provider) — does not choose a provider

## Context and problem

Session cookies (ADR-0003) must work in iPhone Safari and installed PWAs. Safari's tracking prevention blocks third-party cookies, and cross-origin APIs add CORS and preflight complexity.

## Considered options

1. **Same origin:** the PWA static files and `/api/*` are served from one origin (e.g. `https://app.example.com`), with a reverse proxy routing `/api` to the backend.
2. Separate API subdomain (`api.example.com`) with CORS and `SameSite=Lax` same-site cookies — workable but more configuration and more failure modes.
3. Cross-site API with bearer tokens in JavaScript-accessible storage — exposes tokens to XSS.

## Decision

Option 1.

- **Production:** a reverse proxy or platform router serves the built PWA and forwards `/api/*` to the backend container. The backend does not serve static files and has **CORS disabled**.
- **Development:** the Vite dev/preview server proxies `/api` to `localhost:8000`, reproducing the same-origin model.
- The backend trusts `X-Forwarded-*` headers only from configured proxy addresses (`UPCYCLING_FORWARDED_ALLOW_IPS`).
- The PWA must set strict security headers (CSP, `X-Content-Type-Options`, `Referrer-Policy`) at the static-serving layer; defined when hosting is chosen.

## Consequences

- Any hosting choice must support path-based routing on one origin (most PaaS, CDNs and reverse proxies do). The deployment infrastructure stays replaceable.
- No CORS configuration to maintain; cookies are first-party.
- **Reversibility:** moderate; moving to a separate API origin would require CORS, cookie domain changes and re-testing on iOS.
