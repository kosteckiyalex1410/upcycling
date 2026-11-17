"""Voice notes: use cases (ADR-0007). Same idempotent protocol as photos (ADR-0006):

1. `request_upload` creates a `pending` voice note and returns a presigned PUT.
2. The browser PUTs the recording directly to object storage.
3. `complete_upload` re-reads the bytes, verifies size, SHA-256, container, codec and real
   duration, stores the original under a server-only key and marks the note `ready` (or
   `rejected` with a reason code).

No transcription here: transcripts are future, separate records (Slice 2).
"""

import asyncio
import hashlib
import logging
import tempfile
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.application.errors import (
    AudioTooLong,
    IdempotencyConflict,
    NotFound,
    TooManyPendingUploads,
    UnsupportedMediaType,
    UploadIncomplete,
    UploadTooLarge,
    VoiceNoteLimitReached,
)
from app.application.garments import UploadTicket, purge_voice_notes
from app.application.ports import (
    Clock,
    ObjectMissingError,
    ObjectStorage,
    ObjectTooLargeError,
    StorageUnavailableError,
)
from app.config import Settings
from app.domain.media import MediaStatus, RejectionReason
from app.domain.voice_notes import (
    SUPPORTED_AUDIO_TYPES,
    voice_note_audio_key,
    voice_note_staging_key,
)
from app.infrastructure.audio import AudioInfo, AudioRejected, probe_audio
from app.infrastructure.db.garments import GarmentRepository
from app.infrastructure.db.models import VoiceNoteRecord
from app.infrastructure.db.voice_notes import VoiceNoteRepository
from app.infrastructure.storage import hex_to_b64

logger = logging.getLogger(__name__)

# Encoders pad the end of a recording; the client stops at the limit itself.
DURATION_TOLERANCE_MS = 2000


@dataclass(frozen=True, slots=True)
class VoiceNoteUploadRequest:
    client_upload_id: uuid.UUID
    content_type: str  # normalized, parameters stripped
    size_bytes: int
    sha256: str  # lowercase hex
    duration_ms: int | None  # as measured by the browser
    recorded_at: datetime | None


class VoiceNoteService:
    def __init__(
        self, db: AsyncSession, settings: Settings, clock: Clock, storage: ObjectStorage
    ) -> None:
        self._db = db
        self._settings = settings
        self._clock = clock
        self._storage = storage
        self._garments = GarmentRepository(db)
        self._notes = VoiceNoteRepository(db)

    @property
    def _max_duration_ms(self) -> int:
        return self._settings.voice_note_max_seconds * 1000 + DURATION_TOLERANCE_MS

    async def request_upload(
        self, owner_id: uuid.UUID, garment_id: uuid.UUID, request: VoiceNoteUploadRequest
    ) -> tuple[VoiceNoteRecord, UploadTicket | None]:
        if request.content_type not in SUPPORTED_AUDIO_TYPES:
            raise UnsupportedMediaType
        if request.size_bytes > self._settings.voice_note_max_bytes:
            raise UploadTooLarge
        if request.duration_ms is not None and request.duration_ms > self._max_duration_ms:
            raise AudioTooLong

        # Lock the garment row: serializes concurrent uploads so the limit holds.
        garment = await self._garments.get(owner_id, garment_id, for_update=True)
        if garment is None:
            raise NotFound
        existing = await self._notes.get_by_client_upload_id(owner_id, request.client_upload_id)
        if existing is None:
            await self._check_limits(owner_id, garment.id)
        now = self._clock()
        note = existing or await self._notes.insert_or_get(
            owner_id=owner_id,
            client_upload_id=request.client_upload_id,
            values={
                "garment_id": garment.id,
                "status": MediaStatus.PENDING.value,
                "declared_content_type": request.content_type,
                "declared_size_bytes": request.size_bytes,
                "declared_sha256": request.sha256,
                "declared_duration_ms": request.duration_ms,
                "recorded_at": request.recorded_at,
                "created_at": now,
                "updated_at": now,
            },
        )
        await self._db.commit()

        if (
            note.garment_id != garment.id
            or note.declared_sha256 != request.sha256
            or note.declared_size_bytes != request.size_bytes
            or note.declared_content_type != request.content_type
        ):
            raise IdempotencyConflict
        if note.deleted_at is not None:
            raise NotFound
        if note.status != MediaStatus.PENDING.value:
            return note, None
        return note, self._ticket(note, now)

    async def _check_limits(self, owner_id: uuid.UUID, garment_id: uuid.UUID) -> None:
        if await self._notes.count_counted_for_garment(garment_id) >= (
            self._settings.garment_max_voice_notes
        ):
            raise VoiceNoteLimitReached
        since = self._clock() - timedelta(seconds=self._settings.stale_upload_seconds)
        if await self._notes.count_pending_for_owner(owner_id, since=since) >= (
            self._settings.pending_uploads_per_user
        ):
            raise TooManyPendingUploads

    def _ticket(self, note: VoiceNoteRecord, now: datetime) -> UploadTicket:
        ttl = self._settings.upload_url_ttl_seconds
        url, headers = self._storage.presign_put(
            voice_note_staging_key(note.id),
            content_type=note.declared_content_type,
            size_bytes=note.declared_size_bytes,
            sha256_b64=hex_to_b64(note.declared_sha256),
            expires_in=ttl,
        )
        return UploadTicket(url=url, headers=headers, expires_at=now + timedelta(seconds=ttl))

    async def complete_upload(
        self, owner_id: uuid.UUID, garment_id: uuid.UUID, voice_note_id: uuid.UUID
    ) -> VoiceNoteRecord:
        if await self._garments.get(owner_id, garment_id) is None:
            raise NotFound
        note = await self._require(owner_id, voice_note_id)
        if note.garment_id != garment_id:
            raise NotFound
        if note.status != MediaStatus.PENDING.value:
            return note  # already finished: idempotent replay

        key = voice_note_staging_key(note.id)
        if await self._storage.head(key) is None:
            raise UploadIncomplete
        with tempfile.TemporaryFile() as tmp:
            try:
                size = await self._storage.download(
                    key, tmp, max_bytes=self._settings.voice_note_max_bytes
                )
            except ObjectTooLargeError:
                return await self._reject(note, RejectionReason.UPLOAD_TOO_LARGE)
            except ObjectMissingError as exc:
                raise UploadIncomplete from exc
            tmp.seek(0)
            data = tmp.read()
            sha256 = await asyncio.to_thread(_sha256_hex, data)
            try:
                audio = await asyncio.to_thread(self._verify, note, data, sha256)
            except AudioRejected as exc:
                return await self._reject(note, exc.reason)

            audio_key = voice_note_audio_key(note.garment_id, note.id)
            # The original is stored exactly as recorded.
            await self._storage.upload(audio_key, tmp, content_type=audio.content_type)
        now = self._clock()
        await self._notes.finish(
            note.id,
            now=now,
            values={
                "status": MediaStatus.READY.value,
                "content_type": audio.content_type,
                "codec": audio.codec,
                "size_bytes": size,
                "sha256": sha256,
                "duration_ms": audio.duration_ms,
                "audio_key": audio_key,
                "completed_at": now,
            },
        )
        await self._db.commit()
        await self._delete_staging(note.id)
        return await self._require(owner_id, voice_note_id)

    def _verify(self, note: VoiceNoteRecord, data: bytes, sha256: str) -> AudioInfo:
        """The bytes are what the client declared and a supported, complete recording."""
        if len(data) != note.declared_size_bytes or sha256 != note.declared_sha256:
            raise AudioRejected(RejectionReason.CHECKSUM_MISMATCH)
        audio = probe_audio(data)
        if audio.content_type != note.declared_content_type:
            raise AudioRejected(RejectionReason.UNSUPPORTED_MEDIA_TYPE)
        if audio.duration_ms > self._max_duration_ms:
            raise AudioRejected(RejectionReason.AUDIO_TOO_LONG)
        return audio

    async def _reject(self, note: VoiceNoteRecord, reason: RejectionReason) -> VoiceNoteRecord:
        await self._notes.finish(
            note.id,
            now=self._clock(),
            values={"status": MediaStatus.REJECTED.value, "error_code": reason.value},
        )
        await self._db.commit()
        await self._delete_staging(note.id)
        logger.info(
            "voice_note_rejected",
            extra={"fields": {"voice_note_id": note.id, "reason": reason.value}},
        )
        return await self._require(note.owner_id, note.id)

    async def _delete_staging(self, voice_note_id: uuid.UUID) -> None:
        try:
            await self._storage.delete_many([voice_note_staging_key(voice_note_id)])
        except StorageUnavailableError:
            logger.warning(
                "staging_delete_deferred", extra={"fields": {"voice_note_id": voice_note_id}}
            )

    async def delete(self, owner_id: uuid.UUID, voice_note_id: uuid.UUID) -> None:
        """Permanent: the row is hidden at once, then the audio and the row are removed
        (retried by `storage-sweep` if storage fails)."""
        note = await self._require(owner_id, voice_note_id)
        now = self._clock()
        note.deleted_at = now
        note.updated_at = now
        await self._db.commit()
        try:
            await purge_voice_notes(self._db, self._storage, [note])
        except StorageUnavailableError:
            await self._db.rollback()
            logger.warning(
                "voice_note_purge_deferred", extra={"fields": {"voice_note_id": voice_note_id}}
            )

    async def get_ready(self, owner_id: uuid.UUID, voice_note_id: uuid.UUID) -> VoiceNoteRecord:
        note = await self._require(owner_id, voice_note_id)
        if note.status != MediaStatus.READY.value:
            raise NotFound
        return note

    async def _require(self, owner_id: uuid.UUID, voice_note_id: uuid.UUID) -> VoiceNoteRecord:
        note = await self._notes.get(owner_id, voice_note_id)
        if note is None:
            raise NotFound
        return note


def _sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()
