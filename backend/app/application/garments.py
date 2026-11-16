"""Garment projects and their photos: use cases (ADR-0006).

Upload protocol, all steps idempotent so mobile clients can retry any of them:
1. `request_upload` creates a `pending` photo and returns a presigned PUT for a staging key.
2. The browser PUTs the original bytes directly to object storage.
3. `complete` re-reads the bytes, verifies size, SHA-256 and actual image content, writes
   the verified original and JPEG previews under server-only keys, then marks the photo
   `ready` (or `rejected` with a reason code).
"""

import asyncio
import hashlib
import logging
import tempfile
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, BinaryIO

from sqlalchemy.ext.asyncio import AsyncSession

from app.application.errors import (
    IdempotencyConflict,
    MediaLimitReached,
    NotFound,
    TooManyPendingUploads,
    UnsupportedMediaType,
    UploadIncomplete,
    UploadTooLarge,
)
from app.application.ports import (
    Clock,
    ObjectMissingError,
    ObjectStorage,
    ObjectTooLargeError,
    StorageUnavailableError,
)
from app.config import Settings
from app.domain.media import (
    SUPPORTED_CONTENT_TYPES,
    MediaCategory,
    MediaStatus,
    RejectionReason,
    all_keys,
    original_key,
    preview_key,
    staging_key,
    thumbnail_key,
)
from app.infrastructure.db.garments import GarmentListItem, GarmentRepository, MediaRepository
from app.infrastructure.db.models import GarmentRecord, MediaAssetRecord
from app.infrastructure.images import ImageRejected, process_image
from app.infrastructure.storage import hex_to_b64

logger = logging.getLogger(__name__)

_HASH_CHUNK = 1024 * 1024


@dataclass(frozen=True, slots=True)
class UploadTicket:
    url: str
    headers: dict[str, str]
    expires_at: datetime


@dataclass(frozen=True, slots=True)
class UploadRequest:
    client_upload_id: uuid.UUID
    category: MediaCategory
    content_type: str
    size_bytes: int
    sha256: str  # lowercase hex
    filename: str | None


def _clean_text(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    return value or None


def _sha256_hex(source: BinaryIO) -> str:
    source.seek(0)
    digest = hashlib.sha256()
    while chunk := source.read(_HASH_CHUNK):
        digest.update(chunk)
    return digest.hexdigest()


async def purge_media(
    db: AsyncSession, storage: ObjectStorage, media: list[MediaAssetRecord]
) -> None:
    """Delete photos' objects, then their rows. Objects first: if storage fails, the rows
    remain (already marked deleted) and the sweep retries."""
    for record in media:
        await storage.delete_many(all_keys(record.garment_id, record.id))
    await MediaRepository(db).delete_rows([record.id for record in media])
    await db.commit()


class GarmentService:
    def __init__(
        self, db: AsyncSession, settings: Settings, clock: Clock, storage: ObjectStorage
    ) -> None:
        self._db = db
        self._settings = settings
        self._clock = clock
        self._storage = storage
        self._garments = GarmentRepository(db)
        self._media = MediaRepository(db)

    # Garments -------------------------------------------------------------------------

    async def create(
        self,
        owner_id: uuid.UUID,
        *,
        client_request_id: uuid.UUID,
        title: str | None,
        notes: str | None,
    ) -> tuple[GarmentRecord, bool]:
        now = self._clock()
        garment, created = await self._garments.insert_or_get(
            owner_id=owner_id,
            client_request_id=client_request_id,
            values={
                "title": _clean_text(title),
                "notes": _clean_text(notes),
                "created_at": now,
                "updated_at": now,
            },
        )
        await self._db.commit()
        if garment.deleted_at is not None:
            raise NotFound
        return garment, created

    async def list_page(
        self, owner_id: uuid.UUID, *, before_id: uuid.UUID | None, limit: int
    ) -> list[GarmentListItem]:
        return await self._garments.list_page(owner_id, before_id=before_id, limit=limit)

    async def get(
        self, owner_id: uuid.UUID, garment_id: uuid.UUID
    ) -> tuple[GarmentRecord, list[MediaAssetRecord]]:
        garment = await self._require_garment(owner_id, garment_id)
        return garment, await self._media.list_for_garment(owner_id, garment_id)

    async def update(
        self, owner_id: uuid.UUID, garment_id: uuid.UUID, changes: dict[str, str | None]
    ) -> GarmentRecord:
        garment = await self._require_garment(owner_id, garment_id, for_update=True)
        if "title" in changes:
            garment.title = _clean_text(changes["title"])
        if "notes" in changes:
            garment.notes = _clean_text(changes["notes"])
        garment.updated_at = self._clock()
        await self._db.commit()
        return garment

    async def delete(self, owner_id: uuid.UUID, garment_id: uuid.UUID) -> None:
        """Permanently delete a garment and all its photos (ADR-0006). Hidden at once;
        storage cleanup runs now and is retried by `storage-sweep` if it fails."""
        garment = await self._require_garment(owner_id, garment_id, for_update=True)
        media = await self._media.list_for_garment(owner_id, garment_id)
        await self._garments.mark_deleted(garment, now=self._clock())
        await self._db.commit()
        try:
            await purge_media(self._db, self._storage, media)
            await self._garments.delete_row(garment.id)
            await self._db.commit()
        except StorageUnavailableError:
            await self._db.rollback()
            logger.warning("garment_purge_deferred", extra={"fields": {"garment_id": garment_id}})

    async def _require_garment(
        self, owner_id: uuid.UUID, garment_id: uuid.UUID, *, for_update: bool = False
    ) -> GarmentRecord:
        garment = await self._garments.get(owner_id, garment_id, for_update=for_update)
        if garment is None:
            raise NotFound
        return garment

    # Photos ---------------------------------------------------------------------------

    async def request_upload(
        self, owner_id: uuid.UUID, garment_id: uuid.UUID, request: UploadRequest
    ) -> tuple[MediaAssetRecord, UploadTicket | None]:
        if request.content_type not in SUPPORTED_CONTENT_TYPES:
            raise UnsupportedMediaType
        if request.size_bytes > self._settings.upload_max_bytes:
            raise UploadTooLarge

        # Lock the garment row: serializes concurrent uploads so the photo limit holds.
        garment = await self._require_garment(owner_id, garment_id, for_update=True)
        existing = await self._media.get_by_client_upload_id(owner_id, request.client_upload_id)
        if existing is None:
            await self._check_limits(owner_id, garment.id)
        now = self._clock()
        media = existing or await self._media.insert_or_get(
            owner_id=owner_id,
            client_upload_id=request.client_upload_id,
            values={
                "garment_id": garment.id,
                "category": request.category.value,
                "status": MediaStatus.PENDING.value,
                "original_filename": _clean_text(request.filename),
                "declared_content_type": request.content_type,
                "declared_size_bytes": request.size_bytes,
                "declared_sha256": request.sha256,
                "created_at": now,
                "updated_at": now,
            },
        )
        await self._db.commit()

        if (
            media.garment_id != garment.id
            or media.declared_sha256 != request.sha256
            or media.declared_size_bytes != request.size_bytes
            or media.declared_content_type != request.content_type
        ):
            raise IdempotencyConflict
        if media.deleted_at is not None:
            raise NotFound
        if media.status != MediaStatus.PENDING.value:
            return media, None
        return media, self._ticket(media, now)

    async def _check_limits(self, owner_id: uuid.UUID, garment_id: uuid.UUID) -> None:
        if await self._media.count_counted_for_garment(garment_id) >= (
            self._settings.garment_max_photos
        ):
            raise MediaLimitReached
        since = self._clock() - timedelta(seconds=self._settings.stale_upload_seconds)
        if await self._media.count_pending_for_owner(owner_id, since=since) >= (
            self._settings.pending_uploads_per_user
        ):
            raise TooManyPendingUploads

    def _ticket(self, media: MediaAssetRecord, now: datetime) -> UploadTicket:
        ttl = self._settings.upload_url_ttl_seconds
        url, headers = self._storage.presign_put(
            staging_key(media.id),
            content_type=media.declared_content_type,
            size_bytes=media.declared_size_bytes,
            sha256_b64=hex_to_b64(media.declared_sha256),
            expires_in=ttl,
        )
        return UploadTicket(url=url, headers=headers, expires_at=now + timedelta(seconds=ttl))

    async def complete_upload(
        self, owner_id: uuid.UUID, garment_id: uuid.UUID, media_id: uuid.UUID
    ) -> MediaAssetRecord:
        await self._require_garment(owner_id, garment_id)
        media = await self._require_media(owner_id, media_id)
        if media.garment_id != garment_id:
            raise NotFound
        if media.status != MediaStatus.PENDING.value:
            return media  # already finished: idempotent replay

        key = staging_key(media.id)
        if await self._storage.head(key) is None:
            raise UploadIncomplete
        with tempfile.TemporaryFile() as tmp:
            try:
                size = await self._storage.download(
                    key, tmp, max_bytes=self._settings.upload_max_bytes
                )
            except ObjectTooLargeError:
                return await self._reject(media, RejectionReason.UPLOAD_TOO_LARGE)
            except ObjectMissingError as exc:
                raise UploadIncomplete from exc
            sha256 = await asyncio.to_thread(_sha256_hex, tmp)
            if size != media.declared_size_bytes or sha256 != media.declared_sha256:
                return await self._reject(media, RejectionReason.CHECKSUM_MISMATCH)
            try:
                image = await asyncio.to_thread(
                    process_image, tmp, max_pixels=self._settings.image_max_pixels
                )
            except ImageRejected as exc:
                return await self._reject(media, exc.reason)

            keys = {
                "original_key": original_key(media.garment_id, media.id),
                "preview_key": preview_key(media.garment_id, media.id),
                "thumbnail_key": thumbnail_key(media.garment_id, media.id),
            }
            # The original is written from the verified bytes, never re-encoded.
            await self._storage.upload(keys["original_key"], tmp, content_type=image.content_type)
        await self._storage.put_bytes(
            keys["preview_key"], image.preview_jpeg, content_type="image/jpeg"
        )
        await self._storage.put_bytes(
            keys["thumbnail_key"], image.thumbnail_jpeg, content_type="image/jpeg"
        )
        now = self._clock()
        await self._media.finish(
            media.id,
            now=now,
            values={
                "status": MediaStatus.READY.value,
                "content_type": image.content_type,
                "size_bytes": size,
                "sha256": sha256,
                "width": image.width,
                "height": image.height,
                "exif_orientation": image.exif_orientation,
                "completed_at": now,
                **keys,
            },
        )
        await self._db.commit()
        await self._delete_staging(media.id)
        return await self._require_media(owner_id, media_id)

    async def _reject(self, media: MediaAssetRecord, reason: RejectionReason) -> MediaAssetRecord:
        await self._media.finish(
            media.id,
            now=self._clock(),
            values={"status": MediaStatus.REJECTED.value, "error_code": reason.value},
        )
        await self._db.commit()
        await self._delete_staging(media.id)
        logger.info(
            "media_rejected", extra={"fields": {"media_id": media.id, "reason": reason.value}}
        )
        return await self._require_media(media.owner_id, media.id)

    async def _delete_staging(self, media_id: uuid.UUID) -> None:
        try:
            await self._storage.delete_many([staging_key(media_id)])
        except StorageUnavailableError:
            logger.warning("staging_delete_deferred", extra={"fields": {"media_id": media_id}})

    async def set_category(
        self, owner_id: uuid.UUID, media_id: uuid.UUID, category: MediaCategory
    ) -> MediaAssetRecord:
        media = await self._require_media(owner_id, media_id)
        media.category = category.value
        media.updated_at = self._clock()
        await self._db.commit()
        return media

    async def delete_media(self, owner_id: uuid.UUID, media_id: uuid.UUID) -> None:
        media = await self._require_media(owner_id, media_id)
        now = self._clock()
        media.deleted_at = now
        media.updated_at = now
        await self._db.commit()
        try:
            await purge_media(self._db, self._storage, [media])
        except StorageUnavailableError:
            await self._db.rollback()
            logger.warning("media_purge_deferred", extra={"fields": {"media_id": media_id}})

    async def get_ready_media(self, owner_id: uuid.UUID, media_id: uuid.UUID) -> MediaAssetRecord:
        media = await self._require_media(owner_id, media_id)
        if media.status != MediaStatus.READY.value:
            raise NotFound
        return media

    async def _require_media(self, owner_id: uuid.UUID, media_id: uuid.UUID) -> MediaAssetRecord:
        media = await self._media.get(owner_id, media_id)
        if media is None:
            raise NotFound
        return media


# Storage sweep ----------------------------------------------------------------------------


@dataclass(slots=True)
class SweepReport:
    purged_media: int = 0
    purged_garments: int = 0
    removed_staging_objects: int = 0
    removed_orphan_objects: int = 0

    def as_dict(self) -> dict[str, Any]:
        return {
            "purged_media": self.purged_media,
            "purged_garments": self.purged_garments,
            "removed_staging_objects": self.removed_staging_objects,
            "removed_orphan_objects": self.removed_orphan_objects,
        }


# Objects without a database row younger than this may belong to an upload that is being
# completed right now, so they are left alone.
ORPHAN_GRACE = timedelta(hours=1)
_BATCH = 100


def _media_id_from_key(key: str) -> uuid.UUID | None:
    # originals/{garment}/{media} or derived/{garment}/{media}/{file}
    parts = key.split("/")
    try:
        return uuid.UUID(parts[2])
    except (IndexError, ValueError):
        return None


class StorageSweeper:
    """Removes deleted photos/garments, stale unfinished uploads, rejected photos, and
    objects that no row references. Safe to run repeatedly (operator CLI, later the
    Slice 2 worker)."""

    def __init__(
        self, db: AsyncSession, settings: Settings, clock: Clock, storage: ObjectStorage
    ) -> None:
        self._db = db
        self._settings = settings
        self._clock = clock
        self._storage = storage

    async def run(self) -> SweepReport:
        report = SweepReport()
        now = self._clock()
        stale_before = now - timedelta(seconds=self._settings.stale_upload_seconds)
        media_repo = MediaRepository(self._db)
        garment_repo = GarmentRepository(self._db)

        while batch := await media_repo.list_purgeable(stale_before=stale_before, limit=_BATCH):
            await purge_media(self._db, self._storage, batch)
            report.purged_media += len(batch)

        while garments := await garment_repo.list_deleted(limit=_BATCH):
            for garment in garments:
                await garment_repo.delete_row(garment.id)
            await self._db.commit()
            report.purged_garments += len(garments)

        for obj in await self._storage.list_objects("uploads/"):
            if obj.last_modified < stale_before:
                await self._storage.delete_many([obj.key])
                report.removed_staging_objects += 1

        candidates = [
            obj
            for prefix in ("originals/", "derived/")
            for obj in await self._storage.list_objects(prefix)
            if obj.last_modified < now - ORPHAN_GRACE
        ]
        ids = {mid for obj in candidates if (mid := _media_id_from_key(obj.key))}
        known = await media_repo.existing_ids(list(ids))
        for obj in candidates:
            media_id = _media_id_from_key(obj.key)
            if media_id is None or media_id not in known:
                await self._storage.delete_many([obj.key])
                report.removed_orphan_objects += 1
        return report
