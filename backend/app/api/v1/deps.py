"""FastAPI dependencies. `current_user` is the single identity extension point."""

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.auth.sessions import SessionService
from app.application.errors import Unauthenticated
from app.application.ports import Clock, EmailSender, ObjectStorage
from app.config import Settings
from app.domain.users import User


def get_settings(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


async def get_db(request: Request) -> AsyncIterator[AsyncSession]:
    async with request.app.state.session_factory() as session:
        yield session


def get_clock(request: Request) -> Clock:
    clock: Clock = request.app.state.clock
    return clock


def get_email_sender(request: Request) -> EmailSender:
    sender: EmailSender = request.app.state.email_sender
    return sender


def get_storage(request: Request) -> ObjectStorage:
    storage: ObjectStorage = request.app.state.storage
    return storage


SettingsDep = Annotated[Settings, Depends(get_settings)]
DbDep = Annotated[AsyncSession, Depends(get_db)]
ClockDep = Annotated[Clock, Depends(get_clock)]
EmailSenderDep = Annotated[EmailSender, Depends(get_email_sender)]
StorageDep = Annotated[ObjectStorage, Depends(get_storage)]


async def current_user(request: Request, db: DbDep, settings: SettingsDep, clock: ClockDep) -> User:
    token = request.cookies.get(settings.session_cookie_key)
    if not token:
        raise Unauthenticated
    user = await SessionService(db, settings, clock).resolve(token)
    if user is None:
        raise Unauthenticated
    return user


CurrentUser = Annotated[User, Depends(current_user)]
