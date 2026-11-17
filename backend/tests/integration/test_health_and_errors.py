from collections.abc import Callable

import httpx
from fastapi import FastAPI
from pydantic import SecretStr

from app.config import Settings
from app.main import create_app


async def test_liveness(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert response.headers["X-Request-ID"]
    assert response.headers["Cache-Control"] == "no-store"
    assert response.headers["X-Content-Type-Options"] == "nosniff"


async def test_incoming_request_id_is_propagated(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/v1/health", headers={"X-Request-ID": "trace-abcdef12"})
    assert response.headers["X-Request-ID"] == "trace-abcdef12"


async def test_readiness_when_migrated(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/v1/health/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ready"}


async def test_readiness_fails_when_migrations_behind(
    app: FastAPI, client: httpx.AsyncClient
) -> None:
    app.state.expected_migration_head = "9999"
    response = await client.get("/api/v1/health/ready")
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "not_ready"


async def test_unknown_route_uses_error_envelope(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/v1/does-not-exist")
    assert response.status_code == 404
    body = response.json()
    assert body["error"]["code"] == "not_found"
    assert body["error"]["request_id"] == response.headers["X-Request-ID"]


async def test_unhandled_exception_returns_envelope(
    app: FastAPI, client: httpx.AsyncClient
) -> None:
    @app.get("/api/v1/_boom")
    async def boom() -> None:
        raise RuntimeError("secret-internal-detail")

    response = await client.get("/api/v1/_boom")
    assert response.status_code == 500
    assert response.json()["error"]["code"] == "internal_error"
    assert "secret-internal-detail" not in response.text


async def test_docs_disabled_in_production(make_settings: Callable[..., Settings]) -> None:
    settings = make_settings(
        environment="production",
        public_origin="https://upcycling.example",
        secret_key=SecretStr("p" * 48),
        smtp_host="smtp.example",
        smtp_from="Upcycling <no-reply@upcycling.example>",
        smtp_starttls=True,
        storage_endpoint_url="https://s3.storage.example",
        storage_secret_access_key=SecretStr("s" * 40),
    )
    production_app = create_app(settings)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=production_app), base_url="https://testserver"
    ) as http:
        assert (await http.get("/api/v1/openapi.json")).status_code == 404
        assert (await http.get("/api/v1/docs")).status_code == 404
    await production_app.state.engine.dispose()
