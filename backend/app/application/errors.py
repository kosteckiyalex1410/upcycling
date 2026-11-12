"""Application errors carry stable, language-neutral codes (ADR-0004).

The API layer maps each error class to an HTTP status; clients localize by `code`.
"""


class AppError(Exception):
    code: str = "internal_error"
    message: str = "Internal error."

    def __init__(self, message: str | None = None) -> None:
        super().__init__(message or self.message)
        if message:
            self.message = message


class Unauthenticated(AppError):
    code = "unauthenticated"
    message = "Authentication required."


class InvalidLoginToken(AppError):
    code = "invalid_login_token"
    message = "The login link is invalid, expired or already used."


class InvalidLoginCode(AppError):
    code = "invalid_login_code"
    message = "The login code is invalid, expired or already used."


class RateLimited(AppError):
    code = "rate_limited"
    message = "Too many requests. Try again later."

    def __init__(self, retry_after_seconds: int) -> None:
        super().__init__()
        self.retry_after_seconds = retry_after_seconds
