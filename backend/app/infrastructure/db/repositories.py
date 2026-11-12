"""Persistence operations used by application services. Callers own the transaction."""

import uuid
from datetime import datetime

from sqlalchemy import func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.users import Locale, User
from app.infrastructure.db.models import AuthSessionRecord, LoginChallengeRecord, UserRecord


def _to_user(record: UserRecord) -> User:
    return User(
        id=record.id,
        email=record.email,
        preferred_locale=Locale(record.preferred_locale),
        is_active=record.is_active,
    )


class UserRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def get(self, user_id: uuid.UUID) -> User | None:
        record = await self._db.get(UserRecord, user_id)
        return _to_user(record) if record else None

    async def get_by_email(self, email: str) -> User | None:
        record = await self._db.scalar(select(UserRecord).where(UserRecord.email == email))
        return _to_user(record) if record else None

    async def add(self, *, email: str, preferred_locale: Locale) -> User:
        record = UserRecord(email=email, preferred_locale=preferred_locale.value)
        self._db.add(record)
        await self._db.flush()
        await self._db.refresh(record)
        return _to_user(record)

    async def set_preferred_locale(self, user_id: uuid.UUID, locale: Locale) -> User | None:
        # ORM update (not bulk UPDATE) so the identity map and `updated_at` stay consistent.
        record = await self._db.get(UserRecord, user_id)
        if record is None:
            return None
        record.preferred_locale = locale.value
        await self._db.flush()
        await self._db.refresh(record)
        return _to_user(record)


class LoginChallengeRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def count_since(
        self, *, since: datetime, email_hash: str | None = None, ip_hash: str | None = None
    ) -> int:
        query = select(func.count()).select_from(LoginChallengeRecord)
        query = query.where(LoginChallengeRecord.created_at >= since)
        if email_hash is not None:
            query = query.where(LoginChallengeRecord.email_hash == email_hash)
        if ip_hash is not None:
            query = query.where(LoginChallengeRecord.requester_ip_hash == ip_hash)
        return (await self._db.scalar(query)) or 0

    async def oldest_since(
        self, *, since: datetime, email_hash: str | None = None, ip_hash: str | None = None
    ) -> datetime | None:
        query = select(func.min(LoginChallengeRecord.created_at)).where(
            LoginChallengeRecord.created_at >= since
        )
        if email_hash is not None:
            query = query.where(LoginChallengeRecord.email_hash == email_hash)
        if ip_hash is not None:
            query = query.where(LoginChallengeRecord.requester_ip_hash == ip_hash)
        return await self._db.scalar(query)

    async def add(self, record: LoginChallengeRecord) -> LoginChallengeRecord:
        self._db.add(record)
        await self._db.flush()
        return record

    async def get_for_update(self, challenge_id: uuid.UUID) -> LoginChallengeRecord | None:
        return await self._db.scalar(
            select(LoginChallengeRecord)
            .where(LoginChallengeRecord.id == challenge_id)
            .with_for_update()
        )

    async def get_by_token_hash_for_update(self, token_hash: str) -> LoginChallengeRecord | None:
        return await self._db.scalar(
            select(LoginChallengeRecord)
            .where(LoginChallengeRecord.token_hash == token_hash)
            .with_for_update()
        )

    async def claim(
        self, challenge_id: uuid.UUID, *, now: datetime, max_failed_attempts: int
    ) -> bool:
        """Atomically mark a challenge consumed (compare-and-set). Returns False if another
        request consumed it first, or it expired or locked meanwhile."""
        result = await self._db.execute(
            update(LoginChallengeRecord)
            .where(
                LoginChallengeRecord.id == challenge_id,
                LoginChallengeRecord.consumed_at.is_(None),
                LoginChallengeRecord.expires_at > now,
                LoginChallengeRecord.failed_attempts < max_failed_attempts,
            )
            .values(consumed_at=now)
            .returning(LoginChallengeRecord.id)
            .execution_options(synchronize_session=False)
        )
        return result.scalar_one_or_none() is not None

    async def record_failed_attempt(self, challenge_id: uuid.UUID) -> None:
        # Increment in SQL: no lost updates when wrong codes arrive in parallel.
        await self._db.execute(
            update(LoginChallengeRecord)
            .where(LoginChallengeRecord.id == challenge_id)
            .values(failed_attempts=LoginChallengeRecord.failed_attempts + 1)
            .execution_options(synchronize_session=False)
        )

    async def lock_rate_limit_keys(self, *keys: str) -> None:
        """Serialize login requests that share an email or client IP until the transaction
        ends, so the count-then-insert rate-limit check cannot be raced. Keys are hex digests;
        locks are taken in sorted order to rule out deadlocks."""
        for key in sorted(set(keys)):
            await self._db.execute(
                text("SELECT pg_advisory_xact_lock(:key)"), {"key": int(key[:15], 16)}
            )


class AuthSessionRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def add(self, record: AuthSessionRecord) -> AuthSessionRecord:
        self._db.add(record)
        await self._db.flush()
        return record

    async def get_by_token_hash(self, token_hash: str) -> AuthSessionRecord | None:
        return await self._db.scalar(
            select(AuthSessionRecord).where(AuthSessionRecord.token_hash == token_hash)
        )

    async def revoke_by_token_hash(self, token_hash: str, *, now: datetime) -> None:
        await self._db.execute(
            update(AuthSessionRecord)
            .where(AuthSessionRecord.token_hash == token_hash)
            .where(AuthSessionRecord.revoked_at.is_(None))
            .values(revoked_at=now)
        )

    async def revoke_all_for_user(self, user_id: uuid.UUID, *, now: datetime) -> int:
        result = await self._db.execute(
            update(AuthSessionRecord)
            .where(AuthSessionRecord.user_id == user_id)
            .where(AuthSessionRecord.revoked_at.is_(None))
            .values(revoked_at=now)
        )
        return int(getattr(result, "rowcount", 0) or 0)
