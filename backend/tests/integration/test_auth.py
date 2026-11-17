import json
import logging
import re
import uuid
from collections.abc import Callable

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import update

from app.config import Settings
from app.domain.users import Locale, User
from app.infrastructure.db.models import UserRecord
from app.infrastructure.logging import JsonFormatter
from app.main import create_app
from tests.conftest import (
    EXPERT_EMAIL,
    FakeClock,
    RecordingEmailSender,
    create_user,
    login,
    make_client,
)

LOGIN_REQUESTS = "/api/v1/auth/login-requests"
VERIFY_TOKEN = "/api/v1/auth/login-requests/verify-token"


def verify_code_url(challenge_id: str) -> str:
    return f"/api/v1/auth/login-requests/{challenge_id}/verify-code"


async def request_login(client: httpx.AsyncClient, email: str = EXPERT_EMAIL) -> httpx.Response:
    return await client.post(LOGIN_REQUESTS, json={"email": email})


# --- Login request ---------------------------------------------------------------------------


async def test_unknown_email_is_accepted_but_nothing_is_sent(
    client: httpx.AsyncClient, email_sender: RecordingEmailSender
) -> None:
    response = await request_login(client, "nobody@example.com")
    assert response.status_code == 202
    assert set(response.json()) == {"challenge_id", "expires_at"}
    assert email_sender.messages == []


async def test_known_email_receives_localized_link_and_code(
    client: httpx.AsyncClient, email_sender: RecordingEmailSender, user: User
) -> None:
    response = await request_login(client, "  EXPERT@example.com ")
    assert response.status_code == 202
    message = email_sender.last
    assert message.to == EXPERT_EMAIL
    assert "Upcycling" in message.subject
    assert "Ваше посилання" in message.subject  # user's preferred locale is uk
    assert "https://app.test/auth/verify#token=" in message.text_body
    assert email_sender.last_code()


async def test_email_follows_user_locale(
    app: FastAPI, client: httpx.AsyncClient, email_sender: RecordingEmailSender
) -> None:
    await create_user(app, "en@example.com", Locale.EN)
    await request_login(client, "en@example.com")
    assert email_sender.last.subject == "Your Upcycling sign-in link"


async def test_malformed_email_is_rejected(client: httpx.AsyncClient) -> None:
    response = await request_login(client, "not-an-email")
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_failed"
    assert "not-an-email" not in response.text  # input is never echoed


async def test_email_delivery_failure_still_returns_202_and_logs_without_pii(
    client: httpx.AsyncClient,
    email_sender: RecordingEmailSender,
    user: User,
    caplog: pytest.LogCaptureFixture,
) -> None:
    email_sender.fail = True
    with caplog.at_level(logging.INFO):
        response = await request_login(client)
    assert response.status_code == 202
    formatted = "\n".join(JsonFormatter().format(r) for r in caplog.records)
    assert "login_email_send_failed" in formatted
    assert EXPERT_EMAIL not in formatted


# --- Magic link --------------------------------------------------------------------------------


async def test_magic_link_creates_secure_session_cookie(
    client: httpx.AsyncClient, email_sender: RecordingEmailSender, user: User
) -> None:
    await request_login(client)
    response = await client.post(VERIFY_TOKEN, json={"token": email_sender.last_token()})
    assert response.status_code == 200
    assert response.json()["email"] == EXPERT_EMAIL
    cookie = response.headers["set-cookie"].lower()
    assert cookie.startswith("__host-upcycling_session=")  # header lowercased above
    for attribute in ("httponly", "secure", "samesite=lax", "path=/", "max-age="):
        assert attribute in cookie
    assert (await client.get("/api/v1/me")).status_code == 200


async def test_magic_link_is_single_use(
    client: httpx.AsyncClient, email_sender: RecordingEmailSender, user: User
) -> None:
    await request_login(client)
    token = email_sender.last_token()
    assert (await client.post(VERIFY_TOKEN, json={"token": token})).status_code == 200
    second = await client.post(VERIFY_TOKEN, json={"token": token})
    assert second.status_code == 400
    assert second.json()["error"]["code"] == "invalid_login_token"


async def test_magic_link_expires(
    client: httpx.AsyncClient, email_sender: RecordingEmailSender, user: User, clock: FakeClock
) -> None:
    await request_login(client)
    clock.advance(minutes=15, seconds=1)
    response = await client.post(VERIFY_TOKEN, json={"token": email_sender.last_token()})
    assert response.status_code == 400


async def test_unknown_token_is_rejected(client: httpx.AsyncClient) -> None:
    response = await client.post(VERIFY_TOKEN, json={"token": "x" * 43})
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_login_token"


# --- One-time code (installed PWA) --------------------------------------------------------------


async def test_code_creates_session(
    client: httpx.AsyncClient, email_sender: RecordingEmailSender, user: User
) -> None:
    challenge_id = (await request_login(client)).json()["challenge_id"]
    response = await client.post(
        verify_code_url(challenge_id), json={"code": email_sender.last_code()}
    )
    assert response.status_code == 200
    assert (await client.get("/api/v1/me")).status_code == 200


async def test_code_locks_after_max_failed_attempts(
    client: httpx.AsyncClient, email_sender: RecordingEmailSender, user: User
) -> None:
    challenge_id = (await request_login(client)).json()["challenge_id"]
    correct = email_sender.last_code()
    wrong = "000000" if correct != "000000" else "111111"
    for _ in range(5):
        response = await client.post(verify_code_url(challenge_id), json={"code": wrong})
        assert response.json()["error"]["code"] == "invalid_login_code"
    response = await client.post(verify_code_url(challenge_id), json={"code": correct})
    assert response.status_code == 400


async def test_challenge_consumed_by_link_rejects_code(
    client: httpx.AsyncClient, email_sender: RecordingEmailSender, user: User
) -> None:
    challenge_id = (await request_login(client)).json()["challenge_id"]
    code = email_sender.last_code()
    await client.post(VERIFY_TOKEN, json={"token": email_sender.last_token()})
    response = await client.post(verify_code_url(challenge_id), json={"code": code})
    assert response.status_code == 400


async def test_code_for_unknown_email_never_succeeds(
    client: httpx.AsyncClient, email_sender: RecordingEmailSender
) -> None:
    challenge_id = (await request_login(client, "nobody@example.com")).json()["challenge_id"]
    response = await client.post(verify_code_url(challenge_id), json={"code": "123456"})
    assert response.status_code == 400


async def test_code_format_and_unknown_challenge(client: httpx.AsyncClient) -> None:
    malformed = await client.post(verify_code_url(str(uuid.uuid4())), json={"code": "12ab"})
    assert malformed.status_code == 422
    unknown = await client.post(verify_code_url(str(uuid.uuid4())), json={"code": "123456"})
    assert unknown.status_code == 400


# --- Rate limiting -----------------------------------------------------------------------------


async def test_rate_limit_per_email(
    client: httpx.AsyncClient, user: User, clock: FakeClock
) -> None:
    for _ in range(5):
        assert (await request_login(client)).status_code == 202
    limited = await request_login(client)
    assert limited.status_code == 429
    assert limited.json()["error"]["code"] == "rate_limited"
    assert 0 < int(limited.headers["Retry-After"]) <= 15 * 60

    clock.advance(minutes=15, seconds=1)
    assert (await request_login(client)).status_code == 202


async def test_rate_limit_per_ip(
    make_settings: Callable[..., Settings],
    email_sender: RecordingEmailSender,
    clock: FakeClock,
    app: FastAPI,
) -> None:
    limited_app = create_app(
        make_settings(login_rate_limit_per_ip=3), email_sender=email_sender, clock=clock
    )
    async with make_client(limited_app, ip="198.51.100.7") as http:
        for i in range(3):
            assert (await request_login(http, f"user{i}@example.com")).status_code == 202
        assert (await request_login(http, "user9@example.com")).status_code == 429
    async with make_client(limited_app, ip="198.51.100.8") as other_ip:
        assert (await request_login(other_ip, "user9@example.com")).status_code == 202
    await limited_app.state.engine.dispose()


# --- Sessions ----------------------------------------------------------------------------------


async def test_logout_revokes_session_server_side(
    client: httpx.AsyncClient, email_sender: RecordingEmailSender, user: User
) -> None:
    await login(client, email_sender)
    stolen_cookie = client.cookies.get("__Host-upcycling_session")
    response = await client.post("/api/v1/auth/logout")
    assert response.status_code == 204
    assert (await client.get("/api/v1/me")).status_code == 401

    client.cookies.set("__Host-upcycling_session", stolen_cookie or "")
    assert (await client.get("/api/v1/me")).status_code == 401


async def test_logout_without_session_is_idempotent(client: httpx.AsyncClient) -> None:
    assert (await client.post("/api/v1/auth/logout")).status_code == 204


async def test_revoke_all_signs_out_other_devices(
    app: FastAPI, email_sender: RecordingEmailSender, user: User
) -> None:
    async with make_client(app) as phone, make_client(app) as laptop:
        await login(phone, email_sender)
        await login(laptop, email_sender)
        assert (await phone.post("/api/v1/auth/sessions/revoke-all")).status_code == 204
        assert (await phone.get("/api/v1/me")).status_code == 401
        assert (await laptop.get("/api/v1/me")).status_code == 401


async def test_revoke_all_requires_authentication(client: httpx.AsyncClient) -> None:
    assert (await client.post("/api/v1/auth/sessions/revoke-all")).status_code == 401


async def test_session_expires(
    client: httpx.AsyncClient, email_sender: RecordingEmailSender, user: User, clock: FakeClock
) -> None:
    await login(client, email_sender)
    clock.advance(days=30, seconds=1)
    assert (await client.get("/api/v1/me")).status_code == 401


async def test_inactive_user_cannot_log_in_or_use_session(
    app: FastAPI, client: httpx.AsyncClient, email_sender: RecordingEmailSender, user: User
) -> None:
    await login(client, email_sender)
    await request_login(client)
    token = email_sender.last_token()
    async with app.state.session_factory() as db:
        await db.execute(update(UserRecord).values(is_active=False))
        await db.commit()
    assert (await client.get("/api/v1/me")).status_code == 401
    assert (await client.post(VERIFY_TOKEN, json={"token": token})).status_code == 400


# --- CSRF / Origin -----------------------------------------------------------------------------


@pytest.mark.parametrize("origin", [None, "https://evil.example"])
async def test_state_changing_requests_require_allowed_origin(
    app: FastAPI, origin: str | None
) -> None:
    headers = {"Origin": origin} if origin else {}
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="https://testserver", headers=headers
    ) as http:
        response = await http.post(LOGIN_REQUESTS, json={"email": EXPERT_EMAIL})
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "origin_not_allowed"
        assert (await http.get("/api/v1/health")).status_code == 200


# --- Logging hygiene ---------------------------------------------------------------------------


async def test_login_flow_does_not_log_secrets(
    client: httpx.AsyncClient,
    email_sender: RecordingEmailSender,
    user: User,
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.DEBUG):
        await login(client, email_sender)
        await client.get("/api/v1/me")
    session_token = client.cookies.get("__Host-upcycling_session") or ""
    secrets = [email_sender.last_token(), email_sender.last_code(), session_token, EXPERT_EMAIL]
    formatted = "\n".join(JsonFormatter().format(record) for record in caplog.records)
    raw = "\n".join(
        record.getMessage() + json.dumps(getattr(record, "fields", {})) for record in caplog.records
    )
    assert any('"path"' in line for line in formatted.splitlines())  # access log present
    for secret in secrets:
        assert secret not in formatted
        assert secret not in raw


def _unsafe_api_routes(app: FastAPI) -> list[tuple[str, str]]:
    """All state-changing operations, taken from the published OpenAPI contract."""
    routes = []
    for path, operations in app.openapi()["paths"].items():
        for method in operations:
            if method.upper() in {"POST", "PUT", "PATCH", "DELETE"}:
                routes.append((method.upper(), re.sub(r"\{[^}]+\}", str(uuid.uuid4()), path)))
    return routes


@pytest.mark.parametrize("origin", [None, "null", "https://evil.example", "https://app.test.evil"])
async def test_every_state_changing_endpoint_rejects_foreign_origins(
    app: FastAPI,
    client: httpx.AsyncClient,
    email_sender: RecordingEmailSender,
    user: User,
    origin: str | None,
) -> None:
    """Covers endpoints added later automatically, with a valid session cookie present."""
    await login(client, email_sender)
    session_cookie = client.cookies.get("__Host-upcycling_session") or ""
    routes = _unsafe_api_routes(app)
    assert len(routes) >= 12
    headers = {"Origin": origin} if origin else {}
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="https://testserver",
        headers=headers,
        cookies={"__Host-upcycling_session": session_cookie},
    ) as attacker:
        for method, path in routes:
            response = await attacker.request(method, path, json={})
            assert response.status_code == 403, (method, path)
    assert (await client.get("/api/v1/me")).status_code == 200  # session untouched
