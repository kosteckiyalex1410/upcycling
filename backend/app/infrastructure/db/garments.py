"""Persistence for garments and their photos. Every read/write is scoped by `owner_id`;
callers own the transaction."""

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import and_, delete, func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.media import MediaCategory, MediaStatus
from app.infrastructure.db.models import GarmentRecord, MediaAssetRecord


@dataclass(frozen=True, slots=True)
class GarmentListItem:
    garment: GarmentRecord
    photo_count: int
    cover_media_id: uuid.UUID | None


class GarmentRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def insert_or_get(
        self, *, owner_id: uuid.UUID, client_request_id: uuid.UUID, values: dict[str, Any]
    ) -> tuple[GarmentRecord, bool]:
        """Create once per idempotency key; a replay returns the existing row (even if deleted,
        so callers can treat it as not found)."""
        inserted = await self._db.scalar(
            insert(GarmentRecord)
            .values(owner_id=owner_id, client_request_id=client_request_id, **values)
            .on_conflict_do_nothing(constraint="uq_garments_owner_request")
            .returning(GarmentRecord.id)
        )
        record = await self._db.scalar(
            select(GarmentRecord)
            .where(
                GarmentRecord.owner_id == owner_id,
                GarmentRecord.client_request_id == client_request_id,
            )
            .execution_options(populate_existing=True)
        )
        if record is None:  # pragma: no cover - the insert or the conflicting row exists
            raise LookupError("garment vanished after insert")
        return record, inserted is not None

    async def get(
        self, owner_id: uuid.UUID, garment_id: uuid.UUID, *, for_update: bool = False
    ) -> GarmentRecord | None:
        query = select(GarmentRecord).where(
            GarmentRecord.id == garment_id,
            GarmentRecord.owner_id == owner_id,
            GarmentRecord.deleted_at.is_(None),
        )
        if for_update:
            query = query.with_for_update()
        return await self._db.scalar(query)

    async def list_page(
        self, owner_id: uuid.UUID, *, before_id: uuid.UUID | None, limit: int
    ) -> list[GarmentListItem]:
        """Newest first. IDs are time-ordered UUIDv7, so they double as the keyset cursor."""
        ready = and_(
            MediaAssetRecord.garment_id == GarmentRecord.id,
            MediaAssetRecord.status == MediaStatus.READY.value,
            MediaAssetRecord.deleted_at.is_(None),
        )
        photo_count = (
            select(func.count()).select_from(MediaAssetRecord).where(ready).scalar_subquery()
        )
        # Cover: the first front photo, otherwise the first ready photo (categorized or not).
        cover = (
            select(MediaAssetRecord.id)
            .where(ready)
            .order_by(
                (func.coalesce(MediaAssetRecord.category, "") != MediaCategory.FRONT.value).asc(),
                MediaAssetRecord.id.asc(),
            )
            .limit(1)
            .scalar_subquery()
        )
        query = (
            select(GarmentRecord, photo_count, cover)
            .where(GarmentRecord.owner_id == owner_id, GarmentRecord.deleted_at.is_(None))
            .order_by(GarmentRecord.id.desc())
            .limit(limit)
        )
        if before_id is not None:
            query = query.where(GarmentRecord.id < before_id)
        rows = (await self._db.execute(query)).all()
        return [GarmentListItem(row[0], row[1], row[2]) for row in rows]

    async def mark_deleted(self, garment: GarmentRecord, *, now: datetime) -> None:
        garment.deleted_at = now
        await self._db.execute(
            update(MediaAssetRecord)
            .where(MediaAssetRecord.garment_id == garment.id, MediaAssetRecord.deleted_at.is_(None))
            .values(deleted_at=now, updated_at=now)
            .execution_options(synchronize_session=False)
        )

    async def list_deleted(self, *, limit: int) -> list[GarmentRecord]:
        """Across owners: for the storage sweep only."""
        result = await self._db.scalars(
            select(GarmentRecord)
            .where(GarmentRecord.deleted_at.is_not(None))
            .order_by(GarmentRecord.deleted_at)
            .limit(limit)
        )
        return list(result)

    async def delete_row(self, garment_id: uuid.UUID) -> None:
        # Media rows go with it (ON DELETE CASCADE); their objects were deleted first.
        await self._db.execute(delete(GarmentRecord).where(GarmentRecord.id == garment_id))


class MediaRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def insert_or_get(
        self, *, owner_id: uuid.UUID, client_upload_id: uuid.UUID, values: dict[str, Any]
    ) -> MediaAssetRecord:
        await self._db.execute(
            insert(MediaAssetRecord)
            .values(owner_id=owner_id, client_upload_id=client_upload_id, **values)
            .on_conflict_do_nothing(constraint="uq_media_assets_owner_upload")
        )
        record = await self._db.scalar(
            select(MediaAssetRecord)
            .where(
                MediaAssetRecord.owner_id == owner_id,
                MediaAssetRecord.client_upload_id == client_upload_id,
            )
            .execution_options(populate_existing=True)
        )
        if record is None:  # pragma: no cover
            raise LookupError("media vanished after insert")
        return record

    async def get_by_client_upload_id(
        self, owner_id: uuid.UUID, client_upload_id: uuid.UUID
    ) -> MediaAssetRecord | None:
        return await self._db.scalar(
            select(MediaAssetRecord).where(
                MediaAssetRecord.owner_id == owner_id,
                MediaAssetRecord.client_upload_id == client_upload_id,
            )
        )

    async def get(self, owner_id: uuid.UUID, media_id: uuid.UUID) -> MediaAssetRecord | None:
        return await self._db.scalar(
            select(MediaAssetRecord)
            .where(
                MediaAssetRecord.id == media_id,
                MediaAssetRecord.owner_id == owner_id,
                MediaAssetRecord.deleted_at.is_(None),
            )
            .execution_options(populate_existing=True)
        )

    async def list_for_garment(
        self, owner_id: uuid.UUID, garment_id: uuid.UUID
    ) -> list[MediaAssetRecord]:
        result = await self._db.scalars(
            select(MediaAssetRecord)
            .where(
                MediaAssetRecord.garment_id == garment_id,
                MediaAssetRecord.owner_id == owner_id,
                MediaAssetRecord.deleted_at.is_(None),
            )
            .order_by(MediaAssetRecord.id)
        )
        return list(result)

    async def count_counted_for_garment(self, garment_id: uuid.UUID) -> int:
        """Photos that count towards the per-garment limit (pending or ready)."""
        count = await self._db.scalar(
            select(func.count())
            .select_from(MediaAssetRecord)
            .where(
                MediaAssetRecord.garment_id == garment_id,
                MediaAssetRecord.deleted_at.is_(None),
                MediaAssetRecord.status != MediaStatus.REJECTED.value,
            )
        )
        return count or 0

    async def count_pending_for_owner(self, owner_id: uuid.UUID, *, since: datetime) -> int:
        count = await self._db.scalar(
            select(func.count())
            .select_from(MediaAssetRecord)
            .where(
                MediaAssetRecord.owner_id == owner_id,
                MediaAssetRecord.deleted_at.is_(None),
                MediaAssetRecord.status == MediaStatus.PENDING.value,
                MediaAssetRecord.created_at >= since,
            )
        )
        return count or 0

    async def finish(self, media_id: uuid.UUID, *, now: datetime, values: dict[str, Any]) -> bool:
        """Compare-and-set from `pending` to `ready` or `rejected`. False if another request
        finished (or deleted) the photo first."""
        result = await self._db.execute(
            update(MediaAssetRecord)
            .where(
                MediaAssetRecord.id == media_id,
                MediaAssetRecord.status == MediaStatus.PENDING.value,
                MediaAssetRecord.deleted_at.is_(None),
            )
            .values(updated_at=now, **values)
            .returning(MediaAssetRecord.id)
            .execution_options(synchronize_session=False)
        )
        return result.scalar_one_or_none() is not None

    async def list_purgeable(self, *, stale_before: datetime, limit: int) -> list[MediaAssetRecord]:
        """Across owners, for the storage sweep: deleted photos, plus unfinished uploads and
        rejected photos older than `stale_before`."""
        result = await self._db.scalars(
            select(MediaAssetRecord)
            .where(
                (MediaAssetRecord.deleted_at.is_not(None))
                | (
                    MediaAssetRecord.status.in_(
                        [MediaStatus.PENDING.value, MediaStatus.REJECTED.value]
                    )
                    & (MediaAssetRecord.created_at < stale_before)
                )
            )
            .order_by(MediaAssetRecord.id)
            .limit(limit)
        )
        return list(result)

    async def existing_ids(self, ids: list[uuid.UUID]) -> set[uuid.UUID]:
        if not ids:
            return set()
        result = await self._db.scalars(
            select(MediaAssetRecord.id).where(MediaAssetRecord.id.in_(ids))
        )
        return set(result)

    async def delete_rows(self, media_ids: list[uuid.UUID]) -> None:
        if media_ids:
            await self._db.execute(
                delete(MediaAssetRecord).where(MediaAssetRecord.id.in_(media_ids))
            )
