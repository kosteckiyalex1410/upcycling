import hashlib
import hmac
import secrets


def new_token() -> str:
    """256-bit URL-safe random token."""
    return secrets.token_urlsafe(32)


def new_numeric_code(digits: int = 6) -> str:
    return f"{secrets.randbelow(10**digits):0{digits}d}"


def hash_token(token: str) -> str:
    """Unkeyed hash, sufficient for high-entropy random tokens."""
    return hashlib.sha256(token.encode()).hexdigest()


def keyed_digest(secret: str, purpose: str, value: str) -> str:
    """HMAC for low-entropy values (codes, emails, IPs) so stored digests cannot be brute-forced
    without the server secret."""
    return hmac.new(secret.encode(), f"{purpose}:{value}".encode(), hashlib.sha256).hexdigest()


def digests_match(a: str, b: str) -> bool:
    return hmac.compare_digest(a, b)
