# Upcycling — AI Fashion Upcycling Assistant

An iPhone-first expert application that analyzes garments, proposes feasible transformations, and records expert feedback as evidence for future model evaluation.

**Status:** Slice 0 (foundation) — authentication, localization (`uk`/`en`), API contract and quality gates. No garment features yet.

| Document | Purpose |
|---|---|
| [PRODUCT.md](PRODUCT.md) | Product scope and user journeys |
| [ARCHITECTURE.md](ARCHITECTURE.md) | System design, API, data invariants, delivery slices |
| [CLAUDE.md](CLAUDE.md) | Development workflow and guardrails |
| [docs/adr/](docs/adr/0001-record-architecture-decisions.md) | Architecture decision records |
| [docs/development.md](docs/development.md) | Local setup, commands, testing, troubleshooting |
| [docs/follow-ups.md](docs/follow-ups.md) | Known security and operational follow-up tasks |

## Repository layout

```text
backend/                 FastAPI modular monolith (Python 3.13, uv)
  app/api/v1/            HTTP routing and validation
  app/domain/            Domain concepts and invariants
  app/application/       Use cases (auth, users) and ports
  app/infrastructure/    PostgreSQL, SMTP, logging
  app/locales/           Server-generated text (emails) in uk/en
  migrations/            Alembic migrations
packages/api-client/     TypeScript client generated from OpenAPI (committed)
apps/expert-pwa/         React + Vite PWA (Node.js 24, pnpm)
docs/adr/                Architecture decision records
scripts/                 Contract drift check, Docker smoke test
compose.yaml             Local PostgreSQL 18 + Mailpit
```

## Quick start

```bash
cp .env.example .env
make setup            # uv sync + pnpm install
make services-up      # PostgreSQL :55432, Mailpit :1025 / UI :8025
make migrate
make seed-user EMAIL=you@example.com
make dev-api          # terminal 1 — http://localhost:8000/api/v1/docs
make dev-web          # terminal 2 — http://localhost:5173
```

Sign in at <http://localhost:5173>, then open the email in Mailpit at <http://localhost:8025>. See [docs/development.md](docs/development.md) for details.
