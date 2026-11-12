"""Shared fixtures. Integration tests run against a real PostgreSQL database
(`UPCYCLING_TEST_DATABASE_URL`), recreated and migrated once per test session."""

import os
import re
from collections.abc import AsyncIterator, Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import pytest
from alembic import command
from alembic.config import Config
from fastapi import FastAPI
from pydantic import SecretStr
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from app.application.ports import EmailMessage
from app.application.users import UserService
from app.config import Settings
from app.domain.users import Locale, User
from app.main import create_app

BACKEND_ROOT = Path(__file__).resolve().parents[1]
TEST_DATABASE_URL = os.environ.get(
    "UPCYCLING_TEST_DATABASE_URL",
    "postgresql+psycopg://upcycling:upcycling@localhost:55432/upcycling_test",
)
PUBLIC_ORIGIN = "https://app.test"
CLIENT_IP = "203.0.113.10"
EXPERT_EMAIL = "expert@example.com"


def recreate_database(url: str) -> None:
    parsed = make_url(url)
    admin = create_engine(parsed.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(text(f'DROP DATABASE IF EXISTS "{parsed.database}" WITH (FORCE)'))
        conn.execute(text(f'CREATE DATABASE "{parsed.database}"'))
    admin.dispose()


def alembic_config(url: str) -> Config:
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    config.attributes["database_url"] = url
    config.attributes["configure_logger"] = False
    return config


@pytest.fixture(scope="session")
def database_url() -> str:
    recreate_database(TEST_DATABASE_URL)
    command.upgrade(alembic_config(TEST_DATABASE_URL), "head")
    return TEST_DATABASE_URL


class FakeClock:
    def __init__(self) -> None:
        self.now = datetime(2026, 11, 12, 9, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now

    def advance(self, **kwargs: float) -> None:
        self.now += timedelta(**kwargs)


class RecordingEmailSender:
    def __init__(self) -> None:
        self.messages: list[EmailMessage] = []
        self.fail = False

    async def send(self, message: EmailMessage) -> None:
        if self.fail:
            raise ConnectionError(f"SMTP unavailable while sending to {message.to}")
        self.messages.append(message)

    @property
    def last(self) -> EmailMessage:
        return self.messages[-1]

    def last_token(self) -> str:
        match = re.search(r"/auth/verify#token=([A-Za-z0-9_-]+)", self.last.text_body)
        assert match, "no magic link in email"
        return match.group(1)

    def last_code(self) -> str:
        match = re.search(r"^(\d{6})$", self.last.text_body, re.MULTILINE)
        assert match, "no one-time code in email"
        return match.group(1)


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def email_sender() -> RecordingEmailSender:
    return RecordingEmailSender()


@pytest.fixture
def make_settings(database_url: str) -> Callable[..., Settings]:
    def factory(**overrides: Any) -> Settings:
        values: dict[str, Any] = {
            "environment": "test",
            "database_url": database_url,
            "public_origin": PUBLIC_ORIGIN,
            "session_cookie_secure": True,
            "secret_key": SecretStr("test-secret-key-" + "x" * 32),
        }
        values.update(overrides)
        return Settings(_env_file=None, **values)

    return factory


@pytest.fixture
def settings(make_settings: Callable[..., Settings]) -> Settings:
    return make_settings()


@pytest.fixture
async def app(
    settings: Settings, email_sender: RecordingEmailSender, clock: FakeClock, database_url: str
) -> AsyncIterator[FastAPI]:
    application = create_app(settings, email_sender=email_sender, clock=clock)
    yield application
    await application.state.engine.dispose()
    engine = create_engine(database_url)
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE users, login_challenges, auth_sessions CASCADE"))
    engine.dispose()


def make_client(app: FastAPI, *, ip: str = CLIENT_IP) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app, client=(ip, 50000)),
        base_url="https://testserver",
        headers={"Origin": PUBLIC_ORIGIN},
    )


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    async with make_client(app) as http:
        yield http


async def create_user(app: FastAPI, email: str = EXPERT_EMAIL, locale: Locale = Locale.UK) -> User:
    async with app.state.session_factory() as db:
        return await UserService(db).create_user(email=email, preferred_locale=locale)


@pytest.fixture
async def user(app: FastAPI) -> User:
    return await create_user(app)


async def login(
    client: httpx.AsyncClient, email_sender: RecordingEmailSender, email: str = EXPERT_EMAIL
) -> httpx.Response:
    response = await client.post("/api/v1/auth/login-requests", json={"email": email})
    assert response.status_code == 202
    response = await client.post(
        "/api/v1/auth/login-requests/verify-token", json={"token": email_sender.last_token()}
    )
    assert response.status_code == 200, response.text
    return response
