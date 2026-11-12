"""Email login and session endpoints (ADR-0003)."""

import logging
import uuid
from datetime import datetime

from fastapi import APIRouter, BackgroundTasks, Request, Response, status
from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.api.v1.deps import ClockDep, CurrentUser, DbDep, EmailSenderDep, SettingsDep
from app.api.v1.me import MeResponse
from app.application.auth.email_login import EmailLoginService, LoginResult
from app.application.auth.sessions import SessionService
from app.application.ports import EmailMessage, EmailSender
from app.config import Settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequestCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr


class LoginRequestAccepted(BaseModel):
    challenge_id: uuid.UUID = Field(description="Use with the one-time code from the email.")
    expires_at: datetime


class VerifyTokenRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    token: str = Field(min_length=16, max_length=256)


class VerifyCodeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str = Field(pattern=r"^\d{6}$")


async def _send_login_email(sender: EmailSender, message: EmailMessage) -> None:
    try:
        await sender.send(message)
    except Exception:
        logger.exception("login_email_send_failed")


def _set_session_cookie(response: Response, settings: Settings, result: LoginResult) -> None:
    response.set_cookie(
        settings.session_cookie_key,
        result.session.token,
        max_age=settings.session_ttl_seconds,
        expires=result.session.expires_at,
        path="/",
        secure=settings.session_cookie_secure,
        httponly=True,
        samesite="lax",
    )


def _clear_session_cookie(response: Response, settings: Settings) -> None:
    response.delete_cookie(
        settings.session_cookie_key,
        path="/",
        secure=settings.session_cookie_secure,
        httponly=True,
        samesite="lax",
    )


@router.post(
    "/login-requests",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=LoginRequestAccepted,
)
async def create_login_request(
    body: LoginRequestCreate,
    request: Request,
    background_tasks: BackgroundTasks,
    db: DbDep,
    settings: SettingsDep,
    clock: ClockDep,
    email_sender: EmailSenderDep,
) -> LoginRequestAccepted:
    """Always 202 for well-formed input, whether or not the email is registered."""
    client_ip = request.client.host if request.client else "unknown"
    result = await EmailLoginService(db, settings, clock).request_login(
        email=str(body.email), client_ip=client_ip
    )
    if result.email is not None:
        background_tasks.add_task(_send_login_email, email_sender, result.email)
    return LoginRequestAccepted(challenge_id=result.challenge_id, expires_at=result.expires_at)


@router.post("/login-requests/verify-token", response_model=MeResponse)
async def verify_login_token(
    body: VerifyTokenRequest,
    response: Response,
    db: DbDep,
    settings: SettingsDep,
    clock: ClockDep,
) -> MeResponse:
    result = await EmailLoginService(db, settings, clock).verify_token(body.token)
    _set_session_cookie(response, settings, result)
    return MeResponse.from_user(result.user)


@router.post("/login-requests/{challenge_id}/verify-code", response_model=MeResponse)
async def verify_login_code(
    challenge_id: uuid.UUID,
    body: VerifyCodeRequest,
    response: Response,
    db: DbDep,
    settings: SettingsDep,
    clock: ClockDep,
) -> MeResponse:
    result = await EmailLoginService(db, settings, clock).verify_code(challenge_id, body.code)
    _set_session_cookie(response, settings, result)
    return MeResponse.from_user(result.user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(request: Request, db: DbDep, settings: SettingsDep, clock: ClockDep) -> Response:
    """Revoke the current session (idempotent)."""
    token = request.cookies.get(settings.session_cookie_key)
    if token:
        await SessionService(db, settings, clock).revoke(token)
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    _clear_session_cookie(response, settings)
    return response


@router.post("/sessions/revoke-all", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_all_sessions(
    user: CurrentUser, db: DbDep, settings: SettingsDep, clock: ClockDep
) -> Response:
    """Sign out everywhere, including the current device."""
    await SessionService(db, settings, clock).revoke_all(user.id)
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    _clear_session_cookie(response, settings)
    return response
