"""Authentication rules that do not depend on HTTP or persistence (ADR-0003)."""

from datetime import datetime
from enum import StrEnum


class AuthMethod(StrEnum):
    """How a session was established. Passkeys can be added as another member."""

    MAGIC_LINK = "magic_link"
    EMAIL_CODE = "email_code"


def login_challenge_is_usable(
    *,
    expires_at: datetime,
    consumed_at: datetime | None,
    failed_attempts: int,
    max_failed_attempts: int,
    now: datetime,
) -> bool:
    """A challenge is single-use, short-lived and locked after too many wrong codes."""
    return consumed_at is None and now < expires_at and failed_attempts < max_failed_attempts


def session_is_active(*, expires_at: datetime, revoked_at: datetime | None, now: datetime) -> bool:
    return revoked_at is None and now < expires_at
