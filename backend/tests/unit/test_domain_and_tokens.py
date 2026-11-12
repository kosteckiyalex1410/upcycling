from datetime import UTC, datetime, timedelta

from app.application.auth.tokens import hash_token, keyed_digest, new_numeric_code, new_token
from app.domain.auth import login_challenge_is_usable, session_is_active
from app.domain.users import normalize_email

NOW = datetime(2026, 11, 12, 9, 0, tzinfo=UTC)


def _usable(**overrides: object) -> bool:
    values: dict[str, object] = {
        "expires_at": NOW + timedelta(minutes=1),
        "consumed_at": None,
        "failed_attempts": 0,
        "max_failed_attempts": 5,
        "now": NOW,
    }
    values.update(overrides)
    return login_challenge_is_usable(**values)  # type: ignore[arg-type]


def test_login_challenge_usable_when_fresh() -> None:
    assert _usable()


def test_login_challenge_not_usable_when_expired_consumed_or_locked() -> None:
    assert not _usable(expires_at=NOW)
    assert not _usable(consumed_at=NOW)
    assert not _usable(failed_attempts=5)


def test_session_activity() -> None:
    later = NOW + timedelta(days=1)
    assert session_is_active(expires_at=later, revoked_at=None, now=NOW)
    assert not session_is_active(expires_at=later, revoked_at=NOW, now=NOW)
    assert not session_is_active(expires_at=NOW, revoked_at=None, now=NOW)


def test_normalize_email() -> None:
    assert normalize_email("  Expert@Example.COM ") == "expert@example.com"


def test_tokens_are_random_and_hashes_stable() -> None:
    first, second = new_token(), new_token()
    assert first != second
    assert len(first) >= 43
    assert hash_token(first) == hash_token(first)
    assert len(hash_token(first)) == 64


def test_numeric_code_format() -> None:
    for _ in range(100):
        code = new_numeric_code()
        assert len(code) == 6
        assert code.isdigit()


def test_keyed_digest_depends_on_secret_and_purpose() -> None:
    assert keyed_digest("k1", "code", "123456") != keyed_digest("k2", "code", "123456")
    assert keyed_digest("k1", "code", "123456") != keyed_digest("k1", "email", "123456")
