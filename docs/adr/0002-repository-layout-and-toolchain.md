# ADR-0002: Repository layout and toolchain

- **Status:** accepted
- **Date:** 2026-11-12
- **Deciders:** product owner (approved D2, D4, D6, D7), Claude Code (author)

## Context and problem

Slice 0 needs a reproducible repository for a Python backend, a React PWA and a generated TypeScript API client, maintained by a single developer with Claude Code. Future ML work must be able to use its own Python environment without inheriting backend dependencies.

## Considered options

- **Repository:** single monorepo vs separate repositories per app. A monorepo keeps the OpenAPI contract, generated client and PWA in one PR.
- **Python tooling:** uv vs Poetry vs pip-tools. uv is fast, manages Python versions and produces a cross-platform lockfile.
- **JS tooling:** pnpm workspaces vs npm workspaces. pnpm has a strict dependency graph and efficient installs.
- **Task runner:** Make vs just/Taskfile. Make needs no additional install on macOS/Linux.

## Decision

- **Monorepo named `upcycling`** (D6), hosted on **GitHub with GitHub Actions** CI (D2).
- **Backend:** `backend/` is a standalone **uv project** (not a uv workspace root), Python **3.13** (D4), FastAPI, Pydantic v2, SQLAlchemy 2.1 (async, psycopg 3 driver), Alembic, Ruff, mypy (strict), pytest.
- **ML isolation:** future `ml/` components get their own `pyproject.toml`/lockfile and may use a different Python version. They depend on the backend only through exported datasets/manifests or the public API, never by importing `backend/app`.
- **Frontend:** pnpm workspace (`apps/*`, `packages/*`), **Node.js 24 LTS** (D4), pnpm via Corepack (`packageManager` field). React 19, Vite 8, TypeScript 5.9, TanStack Query, React Router, i18next.
- **TypeScript 5.9, not 7:** at setup time `typescript-eslint` requires TypeScript `<6.1` and `openapi-typescript` requires `^5`. Upgrade when both support newer majors.
- **Database:** PostgreSQL **18** (D4) — local via Docker Compose; uses the native `uuidv7()` function for time-ordered primary keys.
- **Containers:** a minimal production-oriented **backend Dockerfile** (D7), built and smoke-tested in CI; no deployment in Slice 0.
- **Task runner:** a root `Makefile` wrapping uv/pnpm/docker commands.
- Exact versions are pinned in `backend/uv.lock` and `pnpm-lock.yaml`; `.python-version` and `.nvmrc` pin runtimes.

## Consequences

- One PR can change the API, regenerate the client and update the PWA atomically.
- Two package managers (uv, pnpm) must be installed by developers; documented in `docs/development.md`.
- Using `uuidv7()` ties primary-key generation to PostgreSQL ≥ 18; acceptable because PostgreSQL is the committed database.
- **Reversibility:** moderate. Splitting the monorepo or replacing the task runner is mechanical; changing ORM/framework is expensive.
