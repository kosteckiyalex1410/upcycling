from typing import Any

from fastapi import APIRouter

from app.api.schemas import ErrorResponse
from app.api.v1 import auth, health, me

# Every operation documents the shared error envelope as its default response (ADR-0004).
_ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    "default": {"model": ErrorResponse, "description": "Error (see `error.code`)."}
}

router = APIRouter(responses=_ERROR_RESPONSES)
router.include_router(health.router)
router.include_router(auth.router)
router.include_router(me.router)
