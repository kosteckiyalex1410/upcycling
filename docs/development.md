# Development guide

## Prerequisites

| Tool | Version | Notes |
|---|---|---|
| Docker (with Compose) | recent | Runs PostgreSQL 18, Mailpit and SeaweedFS (S3-compatible storage) |
| [uv](https://docs.astral.sh/uv/) | ≥ 0.9 | Installs Python 3.13 automatically (`backend/.python-version`) |
| Node.js | 24 LTS | Pinned in `.nvmrc` |
| pnpm | 12.16.1 | Via Corepack: `corepack enable` (version from `package.json` → `packageManager`) |
| GNU Make | any | Task runner (`make help`) |

## First-time setup

```bash
cp .env.example .env          # local configuration; never commit .env
make setup                    # uv sync --locked; pnpm install --frozen-lockfile
make services-up              # PostgreSQL :55432, Mailpit :1025/:8025, S3 storage :8333 (+ bucket/CORS)
make migrate                  # alembic upgrade head
make seed-user EMAIL=you@example.com LOCALE=uk
```

PostgreSQL uses host port **55432** (not 5432) to avoid clashing with a locally installed PostgreSQL.

`make services-up` also runs `storage-init`, which creates the `upcycling` bucket and allows presigned uploads from `UPCYCLING_PUBLIC_ORIGIN` (plus `UPCYCLING_EXTRA_ALLOWED_ORIGINS`). Re-run `make storage-init` after changing those origins.

## Running

```bash
make dev-api    # FastAPI with reload: http://localhost:8000 (OpenAPI UI: /api/v1/docs)
make dev-web    # Vite dev server: http://localhost:5173 — proxies /api to :8000 (same origin, ADR-0005)
```

### Signing in locally

1. Open <http://localhost:5173> and enter the seeded email.
2. Open Mailpit at <http://localhost:8025> — every outgoing email is captured there; nothing is delivered externally.
3. Click the magic link, **or** type the 6-digit code into the app (the code path is what the installed iOS PWA uses, because its cookie jar is separate from Safari — see ADR-0003).

Operator commands:

```bash
cd backend
uv run python -m app.cli create-user --email you@example.com --locale en
uv run python -m app.cli revoke-sessions --email you@example.com   # sign out everywhere
uv run python -m app.cli storage-init    # bucket + CORS rule for browser uploads (idempotent)
uv run python -m app.cli storage-sweep   # purge deleted/stale photos and orphan objects
```

### Photos and storage (ADR-0006)

- The browser uploads each photo **directly to object storage** with a presigned PUT (`http://localhost:8333` locally), then asks the API to verify it. Images are displayed through the API (`/api/v1/media/{id}/thumbnail|preview|original`), never from storage URLs.
- Accepted: JPEG, PNG, HEIC/HEIF up to 30 MB and 100 MP; 40 photos per garment. HEIC is shown via server-rendered JPEG previews, so it works in every browser.
- Inspect stored objects with any S3 client against `http://localhost:8333` (access key `upcycling-dev`, secret `upcycling-dev-storage-secret`, path-style addressing). Keys: `uploads/` (staging), `originals/`, `derived/`.
- Unfinished uploads stay `pending` and appear as "Unfinished upload" in the garment; `make storage-sweep` removes them after 24 h.

## Quality gates

| Command | What it runs |
|---|---|
| `make lint` | Ruff format/lint, Prettier, ESLint (incl. no hardcoded UI strings), locale parity |
| `make typecheck` | mypy (strict), `tsc --build` |
| `make test-backend` | pytest: unit, integration (real PostgreSQL), migration up/down/up + model drift |
| `make test-web` | Vitest + Testing Library |
| `make contract-check` | Fails if `packages/api-client` is stale relative to the backend OpenAPI |
| `make build` | PWA production build + service worker |
| `make test-e2e` | Playwright: Chromium and WebKit (iPhone 15 emulation) against the real API, DB and Mailpit |
| `make docker-smoke` | Builds the backend image; checks non-root user, production config guard, migrations, readiness |
| `make check` | lint + typecheck + tests + contract-check + build (CI minus e2e/docker) |

Backend tests need `make services-up`. They create and drop their own databases (`upcycling_test`, `upcycling_test_migrations`) and use the `upcycling-test` bucket; e2e uses `upcycling_e2e` and the `upcycling-e2e` bucket. Override with `UPCYCLING_TEST_DATABASE_URL` / `UPCYCLING_E2E_DATABASE_URL` and `UPCYCLING_TEST_STORAGE_ENDPOINT` / `UPCYCLING_E2E_STORAGE_ENDPOINT`. Storage is real (SeaweedFS), not mocked.

First e2e run: install browsers with `pnpm --filter @upcycling/expert-pwa exec playwright install chromium webkit`.

CI (`.github/workflows/ci.yml`) runs the same checks in jobs `backend`, `frontend`, `contract`, `e2e` and `docker`.

## Changing the API

1. Change the backend (routes/schemas) and its tests.
2. `make gen-client` — exports `packages/api-client/openapi.json` and regenerates `src/schema.d.ts`.
3. Commit both generated files; `make contract-check` must pass. Within `/api/v1`, make additive changes only (ADR-0004).

## Changing the database

1. Edit `backend/app/infrastructure/db/models.py`.
2. `cd backend && uv run alembic revision --autogenerate -m "describe change"`; review and edit the generated file.
3. `make migrate`; `uv run alembic check` must report no drift; `make test-backend` runs the up/down/up test.

## Adding UI text

All user-facing strings live in `apps/expert-pwa/src/locales/{uk,en}/common.json` (Ukrainian is the default). Add every key to **both** files; plural keys need `_one/_few/_many/_other` in `uk` and `_one/_other` in `en`. `make lint` fails on missing keys or hardcoded JSX text, and `tsc` fails on unknown keys. Server-generated text (emails) lives in `backend/app/locales/`.

## Testing on a real iPhone (manual)

Camera, microphone, service workers, secure cookies and WebCrypto hashing (used for uploads) require HTTPS on a device. Photo uploads also go to a **second origin** (storage), which the iPhone must reach over HTTPS too — an HTTPS page cannot PUT to `http://…:8333` (mixed content). Options:

- **mkcert on the LAN:** create a certificate for your machine's LAN hostname, install the mkcert root CA on the iPhone (Settings → General → About → Certificate Trust Settings), and serve Vite over HTTPS. Set `UPCYCLING_PUBLIC_ORIGIN` to that origin. For storage, put an HTTPS reverse proxy (e.g. Caddy with the same certificate) in front of `:8333` on another port, set `UPCYCLING_STORAGE_PUBLIC_ENDPOINT_URL` to it, and run `make storage-init`.
- **A tunnel** (e.g. Cloudflare Tunnel, ngrok) for both the app and storage — this sends traffic through an external provider; use test data only.

Slice 1 checklist (record results in the PR): camera capture from a category; choosing several photos from the library, including HEIC (does Safari keep HEIC or convert to JPEG? check the format on the photo screen); thumbnails and previews; airplane mode or a weak network during an upload, then Retry; locking the phone or switching apps mid-upload; deleting photos and the garment; the same flow in the installed PWA.

Record results of manual device checks in the PR. Without a device run, report iPhone behaviour as **not verified**.

## Troubleshooting

- **Port 55432/1025/8025 in use:** stop the conflicting service or edit `compose.yaml` and `.env`.
- **`password authentication failed`:** you are hitting a different PostgreSQL; check the port in `UPCYCLING_DATABASE_URL`.
- **Sign-in email not arriving:** check Mailpit is running and `UPCYCLING_SMTP_*` in `.env`; delivery failures are logged as `login_email_send_failed`.
- **Signed out immediately on Safari over plain HTTP:** keep `UPCYCLING_SESSION_COOKIE_SECURE=false` for `http://localhost` only; production enforces `true`.
- **`origin_not_allowed` (403):** the browser origin differs from `UPCYCLING_PUBLIC_ORIGIN`; add extra dev origins via `UPCYCLING_EXTRA_ALLOWED_ORIGINS='["https://…"]'`.
- **Photo upload fails immediately ("Cannot reach the server")** while the API works: the browser cannot reach storage or CORS blocks it. Check `make services-up` (storage healthy), that the page origin is in the bucket CORS rule (`make storage-init` after changing origins), and the browser console for a CORS error.
- **`storage_unavailable` (503):** the API cannot reach `UPCYCLING_STORAGE_ENDPOINT_URL`.

## Production configuration

All production configuration comes from environment variables; nothing secret is committed, and the backend image contains no `.env`. With `UPCYCLING_ENVIRONMENT=production` (the image default) the API **refuses to start** unless:

| Variable | Requirement |
|---|---|
| `UPCYCLING_DATABASE_URL` | Set explicitly; must not be the development URL |
| `UPCYCLING_SECRET_KEY` | Set explicitly; ≥ 32 characters; not the development value (generate with `openssl rand -hex 32`) |
| `UPCYCLING_PUBLIC_ORIGIN` | Set explicitly; `https://` (same for `UPCYCLING_EXTRA_ALLOWED_ORIGINS`) |
| `UPCYCLING_SMTP_HOST`, `UPCYCLING_SMTP_FROM` | Set explicitly; `UPCYCLING_SMTP_STARTTLS=true` or `UPCYCLING_SMTP_USE_TLS=true` |
| `UPCYCLING_SESSION_COOKIE_SECURE` | Must stay `true` (cookie is then named `__Host-upcycling_session`) |
| `UPCYCLING_STORAGE_ENDPOINT_URL`, `UPCYCLING_STORAGE_BUCKET`, `UPCYCLING_STORAGE_ACCESS_KEY_ID`, `UPCYCLING_STORAGE_SECRET_ACCESS_KEY` | Set explicitly; `https://`; not the development secret. Optional `UPCYCLING_STORAGE_PUBLIC_ENDPOINT_URL` (`https://`) when browsers reach storage under a different host than the backend; `UPCYCLING_STORAGE_REGION`, `UPCYCLING_STORAGE_ADDRESSING_STYLE` (`path`/`virtual`) per provider |

Also set `UPCYCLING_SMTP_USERNAME` / `UPCYCLING_SMTP_PASSWORD` as required by the provider, and `UPCYCLING_FORWARDED_ALLOW_IPS` to the reverse proxy's address. `make docker-smoke` verifies that the image rejects the development defaults and can decode HEIC. Open items: [docs/follow-ups.md](follow-ups.md).

**Object storage deployment (ADR-0006).** The bucket must be private, with a credential limited to that bucket, versioning off (or lifecycle rules that purge deleted objects), and this CORS rule — `AllowedOrigins`: the PWA origin(s) only; `AllowedMethods`: `PUT`; `AllowedHeaders`: `content-type`, `x-amz-checksum-sha256`; `ExposeHeaders`: `ETag` — which `python -m app.cli storage-init` applies (it also creates the bucket if the credential may). The provider must honour signed `Content-Length` and `x-amz-checksum-sha256` on presigned PUTs. Schedule `python -m app.cli storage-sweep` (e.g. hourly) until the Slice 2 worker runs it. When the PWA gets a Content-Security-Policy, add the storage origin to `connect-src`.

## Python environments for future ML work

`backend/` is a standalone uv project. Future `ml/` components must use their own `pyproject.toml` and lockfile and must not import `backend/app` (ADR-0002).
