"""Email login: one request yields a magic link and a one-time code (ADR-0003)."""

import math
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.application.auth.sessions import IssuedSession, SessionService
from app.application.auth.tokens import (
    digests_match,
    hash_token,
    keyed_digest,
    new_numeric_code,
    new_token,
)
from app.application.errors import InvalidLoginCode, InvalidLoginToken, RateLimited
from app.application.i18n import translate
from app.application.ports import Clock, EmailMessage
from app.config import Settings
from app.domain.auth import AuthMethod, login_challenge_is_usable
from app.domain.users import User, normalize_email
from app.infrastructure.db.models import LoginChallengeRecord
from app.infrastructure.db.repositories import LoginChallengeRepository, UserRepository


@dataclass(frozen=True, slots=True)
class LoginRequestResult:
    challenge_id: uuid.UUID
    expires_at: datetime
    # None when the email does not belong to an active user; the caller must
    # respond identically in both cases.
    email: EmailMessage | None


@dataclass(frozen=True, slots=True)
class LoginResult:
    user: User
    session: IssuedSession


class EmailLoginService:
    def __init__(self, db: AsyncSession, settings: Settings, clock: Clock) -> None:
        self._db = db
        self._settings = settings
        self._clock = clock
        self._users = UserRepository(db)
        self._challenges = LoginChallengeRepository(db)
        self._sessions = SessionService(db, settings, clock)

    def _digest(self, purpose: str, value: str) -> str:
        return keyed_digest(self._settings.secret_key.get_secret_value(), purpose, value)

    async def request_login(self, *, email: str, client_ip: str) -> LoginRequestResult:
        now = self._clock()
        email = normalize_email(email)
        email_hash = self._digest("email", email)
        ip_hash = self._digest("ip", client_ip)
        await self._enforce_rate_limits(now=now, email_hash=email_hash, ip_hash=ip_hash)

        user = await self._users.get_by_email(email)
        active_user = user if user and user.is_active else None
        token = new_token()
        code = new_numeric_code()
        expires_at = now + timedelta(seconds=self._settings.login_ttl_seconds)
        challenge = await self._challenges.add(
            LoginChallengeRecord(
                user_id=active_user.id if active_user else None,
                email_hash=email_hash,
                requester_ip_hash=ip_hash,
                token_hash=hash_token(token),
                code_hash=self._digest("code", code),
                failed_attempts=0,
                created_at=now,
                expires_at=expires_at,
            )
        )
        await self._db.commit()

        message = None
        if active_user is not None:
            message = self._build_email(active_user, token=token, code=code)
        return LoginRequestResult(challenge_id=challenge.id, expires_at=expires_at, email=message)

    async def verify_token(self, token: str) -> LoginResult:
        challenge = await self._challenges.get_by_token_hash_for_update(hash_token(token))
        if challenge is None or not self._is_usable(challenge) or challenge.user_id is None:
            await self._db.rollback()
            raise InvalidLoginToken
        return await self._complete(challenge, AuthMethod.MAGIC_LINK, InvalidLoginToken)

    async def verify_code(self, challenge_id: uuid.UUID, code: str) -> LoginResult:
        challenge = await self._challenges.get_for_update(challenge_id)
        if challenge is None or not self._is_usable(challenge):
            await self._db.rollback()
            raise InvalidLoginCode
        if challenge.user_id is None or not digests_match(
            self._digest("code", code), challenge.code_hash
        ):
            await self._challenges.record_failed_attempt(challenge.id)
            await self._db.commit()
            raise InvalidLoginCode
        return await self._complete(challenge, AuthMethod.EMAIL_CODE, InvalidLoginCode)

    async def _complete(
        self,
        challenge: LoginChallengeRecord,
        method: AuthMethod,
        error: type[InvalidLoginToken | InvalidLoginCode],
    ) -> LoginResult:
        user = await self._users.get(challenge.user_id) if challenge.user_id else None
        if user is None or not user.is_active:
            await self._db.rollback()
            raise error
        # Single-use guarantee: the row lock serializes verifiers, and the conditional
        # UPDATE is the authoritative check, so at most one request can consume a challenge.
        claimed = await self._challenges.claim(
            challenge.id,
            now=self._clock(),
            max_failed_attempts=self._settings.login_code_max_attempts,
        )
        if not claimed:
            await self._db.rollback()
            raise error
        session = await self._sessions.issue(user.id, method)
        await self._db.commit()
        return LoginResult(user=user, session=session)

    def _is_usable(self, challenge: LoginChallengeRecord) -> bool:
        return login_challenge_is_usable(
            expires_at=challenge.expires_at,
            consumed_at=challenge.consumed_at,
            failed_attempts=challenge.failed_attempts,
            max_failed_attempts=self._settings.login_code_max_attempts,
            now=self._clock(),
        )

    async def _enforce_rate_limits(self, *, now: datetime, email_hash: str, ip_hash: str) -> None:
        await self._challenges.lock_rate_limit_keys(email_hash, ip_hash)
        window = timedelta(seconds=self._settings.login_rate_limit_window_seconds)
        since = now - window
        checks = [
            ({"email_hash": email_hash}, self._settings.login_rate_limit_per_email),
            ({"ip_hash": ip_hash}, self._settings.login_rate_limit_per_ip),
        ]
        for scope, limit in checks:
            if await self._challenges.count_since(since=since, **scope) >= limit:
                oldest = await self._challenges.oldest_since(since=since, **scope)
                retry_after = (oldest + window - now).total_seconds() if oldest else 1
                raise RateLimited(retry_after_seconds=max(1, math.ceil(retry_after)))

    def _build_email(self, user: User, *, token: str, code: str) -> EmailMessage:
        # Token in the URL fragment: never sent to servers or logged by proxies.
        link = f"{self._settings.public_origin}/auth/verify#token={token}"
        minutes = self._settings.login_ttl_seconds // 60
        locale = user.preferred_locale
        return EmailMessage(
            to=user.email,
            subject=translate(locale, "login_email.subject"),
            text_body=translate(locale, "login_email.body", link=link, code=code, minutes=minutes),
        )
