"""SQLAlchemy table mappings. Schema changes require an Alembic migration."""

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    MetaData,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


def _uuid_pk() -> Mapped[uuid.UUID]:
    # PostgreSQL 18 native time-ordered UUIDs (ADR-0002).
    return mapped_column(primary_key=True, server_default=text("uuidv7()"))


class UserRecord(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("preferred_locale IN ('uk', 'en')", name="preferred_locale_supported"),
        CheckConstraint("email = lower(email)", name="email_lowercase"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    email: Mapped[str] = mapped_column(String(320), unique=True)
    preferred_locale: Mapped[str] = mapped_column(String(8), server_default="uk")
    is_active: Mapped[bool] = mapped_column(server_default=text("true"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class LoginChallengeRecord(Base):
    """One email login attempt; also the ledger for rate limiting (ADR-0003).

    Emails and IPs are stored only as HMAC digests. `user_id` is null when the
    requested email does not belong to an active user (nothing is sent).
    """

    __tablename__ = "login_challenges"
    __table_args__ = (
        Index("ix_login_challenges_email_hash_created_at", "email_hash", "created_at"),
        Index(
            "ix_login_challenges_requester_ip_hash_created_at", "requester_ip_hash", "created_at"
        ),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    email_hash: Mapped[str] = mapped_column(String(64))
    requester_ip_hash: Mapped[str] = mapped_column(String(64))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    code_hash: Mapped[str] = mapped_column(String(64))
    failed_attempts: Mapped[int] = mapped_column(server_default=text("0"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AuthSessionRecord(Base):
    """Server-side session; the cookie holds a random token, only its hash is stored."""

    __tablename__ = "auth_sessions"

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    auth_method: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class GarmentRecord(Base):
    """A garment project, the root aggregate for photos (and later analyses and plans).

    `deleted_at` hides the garment immediately; `storage-sweep` / the delete request then
    removes its objects and rows (ADR-0006).
    """

    __tablename__ = "garments"
    __table_args__ = (
        UniqueConstraint("owner_id", "client_request_id", name="uq_garments_owner_request"),
        Index(
            "ix_garments_owner_active",
            "owner_id",
            "id",
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    # Idempotency key from the client: a retried create returns the same garment.
    client_request_id: Mapped[uuid.UUID]
    title: Mapped[str | None] = mapped_column(String(120))
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


_CATEGORIES = "'front', 'back', 'detail', 'fabric', 'defect', 'label'"


class MediaAssetRecord(Base):
    """One original photo of a garment. Declared values come from the client; content
    values are measured by the server from the uploaded bytes and are immutable once
    `status = 'ready'` (only `category` and deletion fields may change afterwards)."""

    __tablename__ = "media_assets"
    __table_args__ = (
        UniqueConstraint("owner_id", "client_upload_id", name="uq_media_assets_owner_upload"),
        CheckConstraint(f"category IN ({_CATEGORIES})", name="category_supported"),
        CheckConstraint("status IN ('pending', 'ready', 'rejected')", name="status_supported"),
        CheckConstraint(
            "status <> 'ready' OR (content_type IS NOT NULL AND size_bytes IS NOT NULL "
            "AND sha256 IS NOT NULL AND width IS NOT NULL AND height IS NOT NULL "
            "AND original_key IS NOT NULL AND preview_key IS NOT NULL "
            "AND thumbnail_key IS NOT NULL AND completed_at IS NOT NULL)",
            name="ready_has_content",
        ),
        CheckConstraint("status <> 'rejected' OR error_code IS NOT NULL", name="rejected_has_code"),
        Index(
            "ix_media_assets_garment_active",
            "garment_id",
            "id",
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index("ix_media_assets_status_created_at", "status", "created_at"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    garment_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("garments.id", ondelete="CASCADE"))
    # Denormalized owner so every media lookup is owner-scoped without a join.
    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    client_upload_id: Mapped[uuid.UUID]
    category: Mapped[str] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(16))
    error_code: Mapped[str | None] = mapped_column(String(64))
    # Display only; never used to build storage keys.
    original_filename: Mapped[str | None] = mapped_column(String(255))
    declared_content_type: Mapped[str] = mapped_column(String(64))
    declared_size_bytes: Mapped[int] = mapped_column(BigInteger)
    declared_sha256: Mapped[str] = mapped_column(String(64))
    content_type: Mapped[str | None] = mapped_column(String(64))
    size_bytes: Mapped[int | None] = mapped_column(BigInteger)
    sha256: Mapped[str | None] = mapped_column(String(64))
    width: Mapped[int | None]
    height: Mapped[int | None]
    exif_orientation: Mapped[int | None] = mapped_column(SmallInteger)
    original_key: Mapped[str | None] = mapped_column(String(255))
    preview_key: Mapped[str | None] = mapped_column(String(255))
    thumbnail_key: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
