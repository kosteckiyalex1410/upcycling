"""Migrations run up -> down -> up on an empty database and match the ORM models."""

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.runtime.migration import MigrationContext
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError

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

    command.upgrade(config, "0001")
    assert _tables(MIGRATIONS_DATABASE_URL) == {"users", "login_challenges", "auth_sessions"}
    command.upgrade(config, "head")
    assert _tables(MIGRATIONS_DATABASE_URL) == set(Base.metadata.tables)
    command.downgrade(config, "0001")
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


def test_media_constraints_protect_ready_and_rejected_states() -> None:
    """A photo cannot be `ready` without verified content, nor `rejected` without a reason,
    nor carry an unknown category — enforced by the database, not only by code."""
    recreate_database(MIGRATIONS_DATABASE_URL)
    command.upgrade(alembic_config(MIGRATIONS_DATABASE_URL), "head")
    engine = create_engine(MIGRATIONS_DATABASE_URL)
    insert_media = text(
        "INSERT INTO media_assets (garment_id, owner_id, client_upload_id, category, status, "
        "error_code, declared_content_type, declared_size_bytes, declared_sha256, created_at, "
        "updated_at) VALUES (:g, :u, gen_random_uuid(), :category, :status, :error, "
        "'image/jpeg', 1, :sha, now(), now())"
    )
    try:
        with engine.begin() as conn:
            user_id = conn.scalar(
                text("INSERT INTO users (email) VALUES ('c@example.com') RETURNING id")
            )
            garment_id = conn.scalar(
                text(
                    "INSERT INTO garments (owner_id, client_request_id, created_at, updated_at) "
                    "VALUES (:u, gen_random_uuid(), now(), now()) RETURNING id"
                ),
                {"u": user_id},
            )
        base = {"g": garment_id, "u": user_id, "sha": "0" * 64, "error": None}
        for values in (
            {"category": "front", "status": "ready"},
            {"category": "front", "status": "rejected"},
            {"category": "sleeve", "status": "pending"},
            {"category": "front", "status": "approved"},
        ):
            with pytest.raises(IntegrityError), engine.begin() as conn:
                conn.execute(insert_media, {**base, **values})
        with engine.begin() as conn:
            conn.execute(insert_media, {**base, "category": "front", "status": "pending"})
    finally:
        engine.dispose()
