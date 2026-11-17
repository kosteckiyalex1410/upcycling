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


class NotFound(AppError):
    """Missing, deleted, or owned by someone else: indistinguishable on purpose."""

    code = "not_found"
    message = "Resource not found."


class IdempotencyConflict(AppError):
    code = "idempotency_conflict"
    message = "This idempotency key was already used with different parameters."


class UnsupportedMediaType(AppError):
    code = "unsupported_media_type"
    message = "This file type is not supported."


class UploadTooLarge(AppError):
    code = "upload_too_large"
    message = "The file exceeds the maximum upload size."


class MediaLimitReached(AppError):
    code = "media_limit_reached"
    message = "This garment already has the maximum number of photos."


class TooManyPendingUploads(AppError):
    code = "too_many_pending_uploads"
    message = "Too many unfinished uploads. Finish or remove some first."


class UploadIncomplete(AppError):
    code = "upload_incomplete"
    message = "The file has not been uploaded yet."


class StorageUnavailable(AppError):
    code = "storage_unavailable"
    message = "File storage is temporarily unavailable. Try again."


class VoiceNoteLimitReached(AppError):
    code = "voice_note_limit_reached"
    message = "This garment already has the maximum number of voice notes."


class AudioTooLong(AppError):
    code = "audio_too_long"
    message = "The recording is longer than allowed."
