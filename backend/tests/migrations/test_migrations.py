"""Migrations run up -> down -> up on an empty database and match the ORM models."""

from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.runtime.migration import MigrationContext
from sqlalchemy import create_engine, inspect
from sqlalchemy.engine import make_url

from app.infrastructure.db.models import Base
from tests.conftest import TEST_DATABASE_URL, alembic_config, recreate_database

MIGRATIONS_DATABASE_URL = (
    make_url(TEST_DATABASE_URL)
    .set(database=f"{make_url(TEST_DATABASE_URL).database}_migrations")
    .render_as_string(hide_password=False)
)


def _tables(url: str) -> set[str]:
    engine = create_engine(url)
    try:
        return set(inspect(engine).get_table_names()) - {"alembic_version"}
    finally:
        engine.dispose()


def test_upgrade_downgrade_upgrade_roundtrip() -> None:
    recreate_database(MIGRATIONS_DATABASE_URL)
    config = alembic_config(MIGRATIONS_DATABASE_URL)

    command.upgrade(config, "head")
    assert _tables(MIGRATIONS_DATABASE_URL) == {"users", "login_challenges", "auth_sessions"}

    command.downgrade(config, "base")
    assert _tables(MIGRATIONS_DATABASE_URL) == set()

    command.upgrade(config, "head")
    assert _tables(MIGRATIONS_DATABASE_URL) == set(Base.metadata.tables)


def test_models_match_migrations() -> None:
    recreate_database(MIGRATIONS_DATABASE_URL)
    command.upgrade(alembic_config(MIGRATIONS_DATABASE_URL), "head")
    engine = create_engine(MIGRATIONS_DATABASE_URL)
    try:
        with engine.connect() as conn:
            context = MigrationContext.configure(conn, opts={"compare_server_default": True})
            assert compare_metadata(context, Base.metadata) == []
    finally:
        engine.dispose()
