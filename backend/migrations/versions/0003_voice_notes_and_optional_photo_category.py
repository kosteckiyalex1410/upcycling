"""Voice notes (ADR-0007) and optional photo category (Slice 1.1).

Existing photos keep their category; new photos may have none.

Downgrade refuses to run while voice notes or uncategorized photos exist: dropping
recordings would destroy evidence, and inventing a category would create false labels.

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-17
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "voice_notes",
        sa.Column("id", sa.Uuid(), server_default=sa.text("uuidv7()"), nullable=False),
        sa.Column("garment_id", sa.Uuid(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("client_upload_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("declared_content_type", sa.String(length=64), nullable=False),
        sa.Column("declared_size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("declared_sha256", sa.String(length=64), nullable=False),
        sa.Column("declared_duration_ms", sa.Integer(), nullable=True),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("content_type", sa.String(length=64), nullable=True),
        sa.Column("codec", sa.String(length=16), nullable=True),
        sa.Column("size_bytes", sa.BigInteger(), nullable=True),
        sa.Column("sha256", sa.String(length=64), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("audio_key", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "content_type IS NULL OR content_type IN ('audio/mp4', 'audio/webm')",
            name=op.f("ck_voice_notes_content_type_supported"),
        ),
        sa.CheckConstraint(
            "status <> 'ready' OR (content_type IS NOT NULL AND codec IS NOT NULL "
            "AND size_bytes IS NOT NULL AND sha256 IS NOT NULL AND duration_ms IS NOT NULL "
            "AND audio_key IS NOT NULL AND completed_at IS NOT NULL)",
            name=op.f("ck_voice_notes_ready_has_content"),
        ),
        sa.CheckConstraint(
            "status <> 'rejected' OR error_code IS NOT NULL",
            name=op.f("ck_voice_notes_rejected_has_code"),
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'ready', 'rejected')",
            name=op.f("ck_voice_notes_status_supported"),
        ),
        sa.ForeignKeyConstraint(
            ["garment_id"],
            ["garments.id"],
            name=op.f("fk_voice_notes_garment_id_garments"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["owner_id"],
            ["users.id"],
            name=op.f("fk_voice_notes_owner_id_users"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_voice_notes")),
        sa.UniqueConstraint("owner_id", "client_upload_id", name="uq_voice_notes_owner_upload"),
    )
    op.create_index(
        "ix_voice_notes_garment_active",
        "voice_notes",
        ["garment_id", "id"],
        unique=False,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.create_index(
        "ix_voice_notes_status_created_at", "voice_notes", ["status", "created_at"], unique=False
    )
    op.alter_column("media_assets", "category", existing_type=sa.VARCHAR(length=16), nullable=True)


def downgrade() -> None:
    bind = op.get_bind()
    voice_notes = bind.scalar(sa.text("SELECT count(*) FROM voice_notes"))
    uncategorized = bind.scalar(sa.text("SELECT count(*) FROM media_assets WHERE category IS NULL"))
    if voice_notes or uncategorized:
        raise RuntimeError(
            f"Refusing to downgrade: {voice_notes} voice notes and {uncategorized} "
            "uncategorized photos would be lost or mislabeled. Export or delete them first."
        )
    op.alter_column("media_assets", "category", existing_type=sa.VARCHAR(length=16), nullable=False)
    op.drop_index("ix_voice_notes_status_created_at", table_name="voice_notes")
    op.drop_index(
        "ix_voice_notes_garment_active",
        table_name="voice_notes",
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.drop_table("voice_notes")
