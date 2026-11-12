from typing import Literal

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.api.errors import error_response
from app.api.v1.deps import DbDep

router = APIRouter(prefix="/health", tags=["health"])


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"


class ReadinessResponse(BaseModel):
    status: Literal["ready"] = "ready"


@router.get("", response_model=HealthResponse)
async def get_health() -> HealthResponse:
    """Liveness: the process is serving requests. Does not touch the database."""
    return HealthResponse()


@router.get("/ready", response_model=ReadinessResponse)
async def get_readiness(request: Request, db: DbDep) -> ReadinessResponse | JSONResponse:
    """Readiness: the database is reachable and migrations are at the expected head."""
    try:
        current = await db.scalar(text("SELECT version_num FROM alembic_version"))
    except SQLAlchemyError:
        return error_response(503, "not_ready", "Database unavailable or not migrated.")
    if current != request.app.state.expected_migration_head:
        return error_response(503, "not_ready", "Database migrations are not at head.")
    return ReadinessResponse()
