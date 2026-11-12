import httpx
import pytest
from fastapi import FastAPI

from app.application.users import InvalidEmail
from app.domain.users import User
from tests.conftest import RecordingEmailSender, create_user, login


async def test_me_requires_authentication(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/v1/me")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthenticated"


async def test_me_rejects_unknown_session_cookie(client: httpx.AsyncClient) -> None:
    client.cookies.set("__Host-upcycling_session", "forged-token-value")
    response = await client.get("/api/v1/me")
    assert response.status_code == 401


async def test_get_me_returns_only_own_profile(
    client: httpx.AsyncClient, email_sender: RecordingEmailSender, user: User
) -> None:
    await login(client, email_sender)
    response = await client.get("/api/v1/me")
    assert response.status_code == 200
    assert response.json() == {"id": str(user.id), "email": user.email, "preferred_locale": "uk"}


async def test_update_preferred_locale_persists(
    client: httpx.AsyncClient, email_sender: RecordingEmailSender, user: User
) -> None:
    await login(client, email_sender)
    response = await client.patch("/api/v1/me", json={"preferred_locale": "en"})
    assert response.status_code == 200
    assert response.json()["preferred_locale"] == "en"
    assert (await client.get("/api/v1/me")).json()["preferred_locale"] == "en"


async def test_update_preferred_locale_validation(
    client: httpx.AsyncClient, email_sender: RecordingEmailSender, user: User
) -> None:
    await login(client, email_sender)
    unsupported = await client.patch("/api/v1/me", json={"preferred_locale": "de"})
    assert unsupported.status_code == 422
    body = unsupported.json()["error"]
    assert body["code"] == "validation_failed"
    assert body["details"][0]["field"] == "preferred_locale"

    extra = await client.patch("/api/v1/me", json={"preferred_locale": "en", "email": "x@y.z"})
    assert extra.status_code == 422


async def test_update_me_requires_authentication(client: httpx.AsyncClient) -> None:
    response = await client.patch("/api/v1/me", json={"preferred_locale": "en"})
    assert response.status_code == 401


async def test_operator_cannot_create_user_with_unusable_email(app: FastAPI) -> None:
    with pytest.raises(InvalidEmail):
        await create_user(app, "expert@example.test")  # rejected by the login endpoint too
