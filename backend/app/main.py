"""Application factory. Run with: uvicorn app.main:create_app --factory"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory
from fastapi import FastAPI
from fastapi.routing import APIRoute

from app.api.errors import register_error_handlers
from app.api.middleware import OriginCheckMiddleware, RequestContextMiddleware
from app.api.v1.router import router as v1_router
from app.application.ports import Clock, EmailSender, ObjectStorage, system_clock
from app.config import Settings, get_settings
from app.infrastructure.db.engine import create_engine, create_session_factory
from app.infrastructure.email import SmtpEmailSender
from app.infrastructure.logging import configure_logging
from app.infrastructure.storage import S3ObjectStorage

BACKEND_ROOT = Path(__file__).resolve().parents[1]
API_PREFIX = "/api/v1"


def _expected_migration_head() -> str | None:
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_ROOT / "migrations"))
    return ScriptDirectory.from_config(config).get_current_head()


def _operation_id(route: APIRoute) -> str:
    # Stable client method names (ADR-0004): the route function name.
    return route.name


def create_app(
    settings: Settings | None = None,
    *,
    email_sender: EmailSender | None = None,
    clock: Clock | None = None,
    storage: ObjectStorage | None = None,
) -> FastAPI:
    settings = settings or get_settings()
    if settings.environment != "test":
        configure_logging(settings.log_level)

    engine = create_engine(settings.database_url)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        yield
        await engine.dispose()

    docs_enabled = not settings.is_production
    app = FastAPI(
        title="Upcycling API",
        version="0.1.0",
        lifespan=lifespan,
        docs_url=f"{API_PREFIX}/docs" if docs_enabled else None,
        redoc_url=None,
        openapi_url=f"{API_PREFIX}/openapi.json" if docs_enabled else None,
        generate_unique_id_function=_operation_id,
    )
    app.state.settings = settings
    app.state.engine = engine
    app.state.session_factory = create_session_factory(engine)
    app.state.clock = clock or system_clock
    app.state.email_sender = email_sender or SmtpEmailSender(settings)
    app.state.storage = storage or S3ObjectStorage(settings)
    app.state.expected_migration_head = _expected_migration_head()

    register_error_handlers(app)
    # Starlette applies the last-added middleware outermost.
    app.add_middleware(OriginCheckMiddleware, allowed_origins=settings.allowed_origins)
    app.add_middleware(RequestContextMiddleware)
    app.include_router(v1_router, prefix=API_PREFIX)
    return app
