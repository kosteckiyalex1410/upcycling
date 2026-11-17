"""Persistence for voice notes. Every owner-facing read/write is scoped by `owner_id`;
callers own the transaction."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import delete, func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.media import MediaStatus
from app.infrastructure.db.models import VoiceNoteRecord


class VoiceNoteRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def insert_or_get(
        self, *, owner_id: uuid.UUID, client_upload_id: uuid.UUID, values: dict[str, Any]
    ) -> VoiceNoteRecord:
        await self._db.execute(
            insert(VoiceNoteRecord)
            .values(owner_id=owner_id, client_upload_id=client_upload_id, **values)
            .on_conflict_do_nothing(constraint="uq_voice_notes_owner_upload")
        )
        record = await self.get_by_client_upload_id(owner_id, client_upload_id)
        if record is None:  # pragma: no cover
            raise LookupError("voice note vanished after insert")
        return record

    async def get_by_client_upload_id(
        self, owner_id: uuid.UUID, client_upload_id: uuid.UUID
    ) -> VoiceNoteRecord | None:
        return await self._db.scalar(
            select(VoiceNoteRecord)
            .where(
                VoiceNoteRecord.owner_id == owner_id,
                VoiceNoteRecord.client_upload_id == client_upload_id,
            )
            .execution_options(populate_existing=True)
        )

    async def get(self, owner_id: uuid.UUID, voice_note_id: uuid.UUID) -> VoiceNoteRecord | None:
        return await self._db.scalar(
            select(VoiceNoteRecord)
            .where(
                VoiceNoteRecord.id == voice_note_id,
                VoiceNoteRecord.owner_id == owner_id,
                VoiceNoteRecord.deleted_at.is_(None),
            )
            .execution_options(populate_existing=True)
        )

    async def list_for_garment(
        self, owner_id: uuid.UUID, garment_id: uuid.UUID
    ) -> list[VoiceNoteRecord]:
        result = await self._db.scalars(
            select(VoiceNoteRecord)
            .where(
                VoiceNoteRecord.garment_id == garment_id,
                VoiceNoteRecord.owner_id == owner_id,
                VoiceNoteRecord.deleted_at.is_(None),
            )
            .order_by(VoiceNoteRecord.id)
        )
        return list(result)

    async def count_counted_for_garment(self, garment_id: uuid.UUID) -> int:
        count = await self._db.scalar(
            select(func.count())
            .select_from(VoiceNoteRecord)
            .where(
                VoiceNoteRecord.garment_id == garment_id,
                VoiceNoteRecord.deleted_at.is_(None),
                VoiceNoteRecord.status != MediaStatus.REJECTED.value,
            )
        )
        return count or 0

    async def count_pending_for_owner(self, owner_id: uuid.UUID, *, since: datetime) -> int:
        count = await self._db.scalar(
            select(func.count())
            .select_from(VoiceNoteRecord)
            .where(
                VoiceNoteRecord.owner_id == owner_id,
                VoiceNoteRecord.deleted_at.is_(None),
                VoiceNoteRecord.status == MediaStatus.PENDING.value,
                VoiceNoteRecord.created_at >= since,
            )
        )
        return count or 0

    async def finish(
        self, voice_note_id: uuid.UUID, *, now: datetime, values: dict[str, Any]
    ) -> bool:
        """Compare-and-set from `pending` to `ready` or `rejected`."""
        result = await self._db.execute(
            update(VoiceNoteRecord)
            .where(
                VoiceNoteRecord.id == voice_note_id,
                VoiceNoteRecord.status == MediaStatus.PENDING.value,
                VoiceNoteRecord.deleted_at.is_(None),
            )
            .values(updated_at=now, **values)
            .returning(VoiceNoteRecord.id)
            .execution_options(synchronize_session=False)
        )
        return result.scalar_one_or_none() is not None

    async def mark_deleted_for_garment(self, garment_id: uuid.UUID, *, now: datetime) -> None:
        await self._db.execute(
            update(VoiceNoteRecord)
            .where(VoiceNoteRecord.garment_id == garment_id, VoiceNoteRecord.deleted_at.is_(None))
            .values(deleted_at=now, updated_at=now)
            .execution_options(synchronize_session=False)
        )

    async def list_purgeable(self, *, stale_before: datetime, limit: int) -> list[VoiceNoteRecord]:
        """Across owners, for the storage sweep: deleted notes, plus unfinished uploads and
        rejected notes older than `stale_before`."""
        result = await self._db.scalars(
            select(VoiceNoteRecord)
            .where(
                (VoiceNoteRecord.deleted_at.is_not(None))
                | (
                    VoiceNoteRecord.status.in_(
                        [MediaStatus.PENDING.value, MediaStatus.REJECTED.value]
                    )
                    & (VoiceNoteRecord.created_at < stale_before)
                )
            )
            .order_by(VoiceNoteRecord.id)
            .limit(limit)
        )
        return list(result)

    async def existing_ids(self, ids: list[uuid.UUID]) -> set[uuid.UUID]:
        if not ids:
            return set()
        result = await self._db.scalars(
            select(VoiceNoteRecord.id).where(VoiceNoteRecord.id.in_(ids))
        )
        return set(result)

    async def delete_rows(self, ids: list[uuid.UUID]) -> None:
        if ids:
            await self._db.execute(delete(VoiceNoteRecord).where(VoiceNoteRecord.id.in_(ids)))
