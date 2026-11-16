"""Server-side sessions, shared by every login method."""

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.application.auth.tokens import hash_token, new_token
from app.application.ports import Clock
from app.config import Settings
from app.domain.auth import AuthMethod, session_is_active
from app.domain.users import User
from app.infrastructure.db.models import AuthSessionRecord
from app.infrastructure.db.repositories import AuthSessionRepository, UserRepository


@dataclass(frozen=True, slots=True)
class IssuedSession:
    token: str
    expires_at: datetime


class SessionService:
    def __init__(self, db: AsyncSession, settings: Settings, clock: Clock) -> None:
        self._db = db
        self._settings = settings
        self._clock = clock
        self._sessions = AuthSessionRepository(db)
        self._users = UserRepository(db)

    async def issue(self, user_id: uuid.UUID, method: AuthMethod) -> IssuedSession:
        """Create a session within the caller's transaction (the caller commits)."""
        now = self._clock()
        token = new_token()
        expires_at = now + timedelta(seconds=self._settings.session_ttl_seconds)
        await self._sessions.add(
            AuthSessionRecord(
                user_id=user_id,
                token_hash=hash_token(token),
                auth_method=method.value,
                created_at=now,
                expires_at=expires_at,
            )
        )
        return IssuedSession(token=token, expires_at=expires_at)

    async def resolve(self, token: str) -> User | None:
        record = await self._sessions.get_by_token_hash(hash_token(token))
        if record is None or not session_is_active(
            expires_at=record.expires_at, revoked_at=record.revoked_at, now=self._clock()
        ):
            return None
        user = await self._users.get(record.user_id)
        return user if user and user.is_active else None

    async def revoke(self, token: str) -> None:
        await self._sessions.revoke_by_token_hash(hash_token(token), now=self._clock())
        await self._db.commit()

    async def revoke_all(self, user_id: uuid.UUID) -> int:
        count = await self._sessions.revoke_all_for_user(user_id, now=self._clock())
        await self._db.commit()
        return count
