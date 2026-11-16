"""Garments and their original photos (media assets); ADR-0006.

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-16
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "garments",
        sa.Column("id", sa.Uuid(), server_default=sa.text("uuidv7()"), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("client_request_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=120), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["owner_id"], ["users.id"], name=op.f("fk_garments_owner_id_users"), ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_garments")),
        sa.UniqueConstraint("owner_id", "client_request_id", name="uq_garments_owner_request"),
    )
    op.create_index(
        "ix_garments_owner_active",
        "garments",
        ["owner_id", "id"],
        unique=False,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.create_table(
        "media_assets",
        sa.Column("id", sa.Uuid(), server_default=sa.text("uuidv7()"), nullable=False),
        sa.Column("garment_id", sa.Uuid(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("client_upload_id", sa.Uuid(), nullable=False),
        sa.Column("category", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("original_filename", sa.String(length=255), nullable=True),
        sa.Column("declared_content_type", sa.String(length=64), nullable=False),
        sa.Column("declared_size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("declared_sha256", sa.String(length=64), nullable=False),
        sa.Column("content_type", sa.String(length=64), nullable=True),
        sa.Column("size_bytes", sa.BigInteger(), nullable=True),
        sa.Column("sha256", sa.String(length=64), nullable=True),
        sa.Column("width", sa.Integer(), nullable=True),
        sa.Column("height", sa.Integer(), nullable=True),
        sa.Column("exif_orientation", sa.SmallInteger(), nullable=True),
        sa.Column("original_key", sa.String(length=255), nullable=True),
        sa.Column("preview_key", sa.String(length=255), nullable=True),
        sa.Column("thumbnail_key", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "category IN ('front', 'back', 'detail', 'fabric', 'defect', 'label')",
            name=op.f("ck_media_assets_category_supported"),
        ),
        sa.CheckConstraint(
            "status <> 'ready' OR (content_type IS NOT NULL AND size_bytes IS NOT NULL "
            "AND sha256 IS NOT NULL AND width IS NOT NULL AND height IS NOT NULL "
            "AND original_key IS NOT NULL AND preview_key IS NOT NULL "
            "AND thumbnail_key IS NOT NULL AND completed_at IS NOT NULL)",
            name=op.f("ck_media_assets_ready_has_content"),
        ),
        sa.CheckConstraint(
            "status <> 'rejected' OR error_code IS NOT NULL",
            name=op.f("ck_media_assets_rejected_has_code"),
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'ready', 'rejected')",
            name=op.f("ck_media_assets_status_supported"),
        ),
        sa.ForeignKeyConstraint(
            ["garment_id"],
            ["garments.id"],
            name=op.f("fk_media_assets_garment_id_garments"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["owner_id"],
            ["users.id"],
            name=op.f("fk_media_assets_owner_id_users"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_media_assets")),
        sa.UniqueConstraint("owner_id", "client_upload_id", name="uq_media_assets_owner_upload"),
    )
    op.create_index(
        "ix_media_assets_garment_active",
        "media_assets",
        ["garment_id", "id"],
        unique=False,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.create_index(
        "ix_media_assets_status_created_at", "media_assets", ["status", "created_at"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_media_assets_status_created_at", table_name="media_assets")
    op.drop_index(
        "ix_media_assets_garment_active",
        table_name="media_assets",
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.drop_table("media_assets")
    op.drop_index(
        "ix_garments_owner_active",
        table_name="garments",
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.drop_table("garments")
