# Development guide

## Prerequisites

| Tool | Version | Notes |
|---|---|---|
| Docker (with Compose) | recent | Runs PostgreSQL 18 and Mailpit |
| [uv](https://docs.astral.sh/uv/) | ≥ 0.9 | Installs Python 3.13 automatically (`backend/.python-version`) |
| Node.js | 24 LTS | Pinned in `.nvmrc` |
| pnpm | 12.16.1 | Via Corepack: `corepack enable` (version from `package.json` → `packageManager`) |
| GNU Make | any | Task runner (`make help`) |

## First-time setup

```bash
cp .env.example .env          # local configuration; never commit .env
make setup                    # uv sync --locked; pnpm install --frozen-lockfile
make services-up              # docker compose: PostgreSQL on 127.0.0.1:55432, Mailpit on :1025/:8025
make migrate                  # alembic upgrade head
make seed-user EMAIL=you@example.com LOCALE=uk
```

PostgreSQL uses host port **55432** (not 5432) to avoid clashing with a locally installed PostgreSQL.

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
```

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

Backend tests need `make services-up`. They create and drop their own databases (`upcycling_test`, `upcycling_test_migrations`); e2e uses `upcycling_e2e`. Override with `UPCYCLING_TEST_DATABASE_URL` / `UPCYCLING_E2E_DATABASE_URL`.

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

Camera, microphone, service workers and secure cookies require HTTPS on a device. Options:

- **mkcert on the LAN:** create a certificate for your machine's LAN hostname, install the mkcert root CA on the iPhone (Settings → General → About → Certificate Trust Settings), and serve Vite over HTTPS. Set `UPCYCLING_PUBLIC_ORIGIN` to that origin.
- **A tunnel** (e.g. Cloudflare Tunnel, ngrok) — this sends traffic through an external provider; use test data only.

Record results of manual device checks in the PR. Without a device run, report iPhone behaviour as **not verified**.

## Troubleshooting

- **Port 55432/1025/8025 in use:** stop the conflicting service or edit `compose.yaml` and `.env`.
- **`password authentication failed`:** you are hitting a different PostgreSQL; check the port in `UPCYCLING_DATABASE_URL`.
- **Sign-in email not arriving:** check Mailpit is running and `UPCYCLING_SMTP_*` in `.env`; delivery failures are logged as `login_email_send_failed`.
- **Signed out immediately on Safari over plain HTTP:** keep `UPCYCLING_SESSION_COOKIE_SECURE=false` for `http://localhost` only; production enforces `true`.
- **`origin_not_allowed` (403):** the browser origin differs from `UPCYCLING_PUBLIC_ORIGIN`; add extra dev origins via `UPCYCLING_EXTRA_ALLOWED_ORIGINS='["https://…"]'`.

## Production configuration

All production configuration comes from environment variables; nothing secret is committed, and the backend image contains no `.env`. With `UPCYCLING_ENVIRONMENT=production` (the image default) the API **refuses to start** unless:

| Variable | Requirement |
|---|---|
| `UPCYCLING_DATABASE_URL` | Set explicitly; must not be the development URL |
| `UPCYCLING_SECRET_KEY` | Set explicitly; ≥ 32 characters; not the development value (generate with `openssl rand -hex 32`) |
| `UPCYCLING_PUBLIC_ORIGIN` | Set explicitly; `https://` (same for `UPCYCLING_EXTRA_ALLOWED_ORIGINS`) |
| `UPCYCLING_SMTP_HOST`, `UPCYCLING_SMTP_FROM` | Set explicitly; `UPCYCLING_SMTP_STARTTLS=true` or `UPCYCLING_SMTP_USE_TLS=true` |
| `UPCYCLING_SESSION_COOKIE_SECURE` | Must stay `true` (cookie is then named `__Host-upcycling_session`) |

Also set `UPCYCLING_SMTP_USERNAME` / `UPCYCLING_SMTP_PASSWORD` as required by the provider, and `UPCYCLING_FORWARDED_ALLOW_IPS` to the reverse proxy's address. `make docker-smoke` verifies that the image rejects the development defaults. Open items: [docs/follow-ups.md](follow-ups.md).

## Python environments for future ML work

`backend/` is a standalone uv project. Future `ml/` components must use their own `pyproject.toml` and lockfile and must not import `backend/app` (ADR-0002).
