"""Concurrency guarantees of email login (ADR-0003).

Each request uses its own database connection. A delay is injected right after the
challenge is read (or the rate limit counted), so every request reads the same state
before any of them writes. Without correct locking/compare-and-set these tests fail.
"""

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import func, select

from app.config import Settings
from app.domain.users import User
from app.infrastructure.db.models import AuthSessionRecord
from app.infrastructure.db.repositories import LoginChallengeRepository
from app.main import create_app
from tests.conftest import FakeClock, RecordingEmailSender, make_client

PARALLEL = 8
RACE_WINDOW_SECONDS = 0.05
LOGIN_REQUESTS = "/api/v1/auth/login-requests"
VERIFY_TOKEN = "/api/v1/auth/login-requests/verify-token"


def _delay_after(method: Callable[..., Awaitable[Any]]) -> Callable[..., Awaitable[Any]]:
    async def delayed(*args: Any, **kwargs: Any) -> Any:
        result = await method(*args, **kwargs)
        await asyncio.sleep(RACE_WINDOW_SECONDS)
        return result

    return delayed


@pytest.fixture
def widen_race_window(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("get_for_update", "get_by_token_hash_for_update", "count_since"):
        monkeypatch.setattr(
            LoginChallengeRepository, name, _delay_after(getattr(LoginChallengeRepository, name))
        )


async def _parallel_posts(app: FastAPI, url: str, payloads: list[dict[str, str]]) -> list[int]:
    clients = [make_client(app) for _ in payloads]
    try:
        responses = await asyncio.gather(
            *(c.post(url, json=p) for c, p in zip(clients, payloads, strict=True))
        )
    finally:
        await asyncio.gather(*(c.aclose() for c in clients))
    return [r.status_code for r in responses]


async def _session_count(app: FastAPI) -> int:
    async with app.state.session_factory() as db:
        return int(await db.scalar(select(func.count()).select_from(AuthSessionRecord)) or 0)


async def _code_url(client: httpx.AsyncClient, user: User) -> str:
    response = await client.post(LOGIN_REQUESTS, json={"email": user.email})
    return f"{LOGIN_REQUESTS}/{response.json()['challenge_id']}/verify-code"


@pytest.mark.usefixtures("widen_race_window")
async def test_concurrent_magic_link_use_creates_exactly_one_session(
    app: FastAPI, client: httpx.AsyncClient, email_sender: RecordingEmailSender, user: User
) -> None:
    await client.post(LOGIN_REQUESTS, json={"email": user.email})
    token = email_sender.last_token()
    statuses = await _parallel_posts(app, VERIFY_TOKEN, [{"token": token}] * PARALLEL)
    assert sorted(statuses) == [200] + [400] * (PARALLEL - 1)
    assert await _session_count(app) == 1


@pytest.mark.usefixtures("widen_race_window")
async def test_concurrent_code_use_creates_exactly_one_session(
    app: FastAPI, client: httpx.AsyncClient, email_sender: RecordingEmailSender, user: User
) -> None:
    url = await _code_url(client, user)
    statuses = await _parallel_posts(app, url, [{"code": email_sender.last_code()}] * PARALLEL)
    assert sorted(statuses) == [200] + [400] * (PARALLEL - 1)
    assert await _session_count(app) == 1


@pytest.mark.usefixtures("widen_race_window")
async def test_concurrent_link_and_code_cannot_both_succeed(
    app: FastAPI, client: httpx.AsyncClient, email_sender: RecordingEmailSender, user: User
) -> None:
    code_url = await _code_url(client, user)
    async with make_client(app) as a, make_client(app) as b:
        results = await asyncio.gather(
            a.post(VERIFY_TOKEN, json={"token": email_sender.last_token()}),
            b.post(code_url, json={"code": email_sender.last_code()}),
        )
    assert sorted(r.status_code for r in results) == [200, 400]
    assert await _session_count(app) == 1


@pytest.mark.usefixtures("widen_race_window")
async def test_concurrent_wrong_codes_are_all_counted(
    app: FastAPI, client: httpx.AsyncClient, email_sender: RecordingEmailSender, user: User
) -> None:
    """No lost updates on the failed-attempt counter: parallel guessing cannot bypass lockout."""
    url = await _code_url(client, user)
    correct = email_sender.last_code()
    wrong = "000000" if correct != "000000" else "111111"
    statuses = await _parallel_posts(app, url, [{"code": wrong}] * PARALLEL)
    assert statuses == [400] * PARALLEL
    assert (await client.post(url, json={"code": correct})).status_code == 400
    assert await _session_count(app) == 0


@pytest.mark.usefixtures("widen_race_window")
async def test_concurrent_login_requests_respect_rate_limit(
    make_settings: Callable[..., Settings],
    email_sender: RecordingEmailSender,
    clock: FakeClock,
    app: FastAPI,
    user: User,
) -> None:
    limited_app = create_app(
        make_settings(login_rate_limit_per_email=3), email_sender=email_sender, clock=clock
    )
    try:
        statuses = await _parallel_posts(
            limited_app, LOGIN_REQUESTS, [{"email": user.email}] * PARALLEL
        )
    finally:
        await limited_app.state.engine.dispose()
    assert sorted(statuses) == [202] * 3 + [429] * (PARALLEL - 3)
