# ADR-0004: API contract conventions and TypeScript client generation

- **Status:** accepted
- **Date:** 2026-11-12
- **Deciders:** product owner (approved plan), Claude Code (author)

## Context and problem

The API under `/api/v1` is the stable boundary between the backend and any client (PWA now, native later). `CLAUDE.md` forbids handwritten DTOs that can diverge from the backend schema. Errors must be machine-readable and language-neutral so clients can localize them.

## Considered options

- **Generator:** `openapi-typescript` + `openapi-fetch` (types only + ~6 kB fetch wrapper) vs Orval / `@hey-api/openapi-ts` (generate hooks and more runtime code, tighter coupling to the generator).
- **Spec source:** export from the FastAPI app object vs fetch from a running server.

## Decision

- **Generator:** `openapi-typescript` generates `packages/api-client/src/schema.d.ts`; `openapi-fetch` provides the typed runtime client. TanStack Query hooks are written per feature on top of it.
- **Spec export:** `backend/scripts/export_openapi.py` imports `create_app()` (no server, no database) and writes `packages/api-client/openapi.json` with sorted keys. Both the spec and generated types are **committed** so contract changes appear in diffs.
- **Drift gate:** `make contract-check` regenerates into a temporary directory and fails if the committed files differ. Runs in CI.
- **Operation IDs:** the route function name (e.g. `get_me`), via a custom `generate_unique_id_function`; stable across refactors of paths.
- **Error envelope** (all non-2xx responses, documented as the `default` response):
  ```json
  {"error": {"code": "unauthenticated", "message": "Authentication required.", "request_id": "…", "details": []}}
  ```
  `code` is a stable, language-neutral identifier; `message` is developer-facing English. Clients map `code` to localized text (`errors.<code>`). Validation errors use `code: "validation_failed"` with per-field `details`.
- **Breaking changes:** within `/api/v1`, only additive changes. An automated breaking-change check (e.g. `oasdiff`) becomes a blocking CI gate from Slice 1, once a baseline exists on `main`.

## Consequences

- No handwritten DTOs; type errors surface in the PWA build when the API changes.
- The generated client is framework-neutral and reusable by a future React Native / Capacitor client.
- Committed generated files add diff noise; mitigated by deterministic output.
- **Reversibility:** high; switching generators touches only `packages/api-client` and call sites.
