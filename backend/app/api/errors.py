"""Maps exceptions to the error envelope. Messages never echo request input."""

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.schemas import ErrorBody, ErrorDetail, ErrorResponse
from app.application.errors import (
    AppError,
    IdempotencyConflict,
    InvalidLoginCode,
    InvalidLoginToken,
    MediaLimitReached,
    NotFound,
    RateLimited,
    StorageUnavailable,
    TooManyPendingUploads,
    Unauthenticated,
    UnsupportedMediaType,
    UploadIncomplete,
    UploadTooLarge,
)
from app.application.ports import StorageUnavailableError
from app.infrastructure.logging import request_id_var

logger = logging.getLogger(__name__)

_STATUS_BY_ERROR: dict[type[AppError], int] = {
    Unauthenticated: 401,
    InvalidLoginToken: 400,
    InvalidLoginCode: 400,
    RateLimited: 429,
    NotFound: 404,
    IdempotencyConflict: 409,
    UnsupportedMediaType: 415,
    UploadTooLarge: 413,
    MediaLimitReached: 409,
    TooManyPendingUploads: 409,
    UploadIncomplete: 409,
    StorageUnavailable: 503,
}

_HTTP_CODES = {404: "not_found", 405: "method_not_allowed"}


def error_response(
    status_code: int,
    code: str,
    message: str,
    details: list[ErrorDetail] | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    body = ErrorResponse(
        error=ErrorBody(
            code=code, message=message, request_id=request_id_var.get(), details=details or []
        )
    )
    return JSONResponse(body.model_dump(mode="json"), status_code=status_code, headers=headers)


async def _handle_app_error(_: Request, exc: Exception) -> JSONResponse:
    if not isinstance(exc, AppError):
        raise exc
    headers = None
    if isinstance(exc, RateLimited):
        headers = {"Retry-After": str(exc.retry_after_seconds)}
    status = _STATUS_BY_ERROR.get(type(exc), 500)
    return error_response(status, exc.code, exc.message, headers=headers)


async def _handle_storage_unavailable(_: Request, exc: Exception) -> JSONResponse:
    logger.warning("storage_unavailable", exc_info=exc)
    error = StorageUnavailable()
    return error_response(503, error.code, error.message, headers={"Retry-After": "5"})


async def _handle_validation_error(_: Request, exc: Exception) -> JSONResponse:
    if not isinstance(exc, RequestValidationError):
        raise exc
    details = [
        ErrorDetail(
            field=".".join(str(part) for part in err["loc"][1:]) or None,
            code=str(err["type"]),
            message=str(err["msg"]),
        )
        for err in exc.errors()
    ]
    return error_response(422, "validation_failed", "Request validation failed.", details)


async def _handle_http_error(_: Request, exc: Exception) -> JSONResponse:
    if not isinstance(exc, StarletteHTTPException):
        raise exc
    code = _HTTP_CODES.get(exc.status_code, "http_error")
    return error_response(
        exc.status_code, code, str(exc.detail), headers=dict(exc.headers) if exc.headers else None
    )


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AppError, _handle_app_error)
    app.add_exception_handler(StorageUnavailableError, _handle_storage_unavailable)
    app.add_exception_handler(RequestValidationError, _handle_validation_error)
    app.add_exception_handler(StarletteHTTPException, _handle_http_error)
