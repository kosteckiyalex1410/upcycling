# syntax=docker/dockerfile:1
# Production-oriented backend image (ADR-0002). The same image will run the API and,
# from Slice 2, the worker. Deployment is out of scope for Slice 0.

FROM ghcr.io/astral-sh/uv:0.9.26 AS uv

FROM python:3.13.18-slim-trixie AS build
COPY --from=uv /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/opt/venv
WORKDIR /app
COPY pyproject.toml uv.lock .python-version ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-install-project

FROM python:3.13.18-slim-trixie AS runtime
ENV PATH=/opt/venv/bin:$PATH \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UPCYCLING_ENVIRONMENT=production \
    UPCYCLING_FORWARDED_ALLOW_IPS=127.0.0.1
RUN groupadd --system --gid 10001 app \
    && useradd --system --uid 10001 --gid app --no-create-home --home-dir /app app
WORKDIR /app
COPY --from=build /opt/venv /opt/venv
COPY alembic.ini ./
COPY migrations ./migrations
COPY app ./app
USER app
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health', timeout=2)"]
# Migrations are a separate release step: `docker run <image> alembic upgrade head`.
# Trust X-Forwarded-* only from the reverse proxy given in UPCYCLING_FORWARDED_ALLOW_IPS (ADR-0005).
CMD ["sh", "-c", "exec uvicorn app.main:create_app --factory --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips \"$UPCYCLING_FORWARDED_ALLOW_IPS\" --timeout-keep-alive 75"]
