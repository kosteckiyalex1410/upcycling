"""Voice note response schema, shared by the garment and voice note routes (ADR-0007)."""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.domain.media import MediaStatus
from app.infrastructure.db.models import VoiceNoteRecord


class VoiceNote(BaseModel):
    id: uuid.UUID
    garment_id: uuid.UUID
    status: MediaStatus
    error_code: str | None = Field(description="Set when `status` is `rejected`.")
    content_type: str | None = Field(description="Container detected from the bytes.")
    codec: str | None = Field(description="`aac` or `opus`; set when ready.")
    size_bytes: int | None
    sha256: str | None = Field(description="Hex SHA-256 of the stored original recording.")
    duration_ms: int | None = Field(description="Measured by the server; set when ready.")
    recorded_at: datetime | None = Field(description="Device time when recording started.")
    created_at: datetime
    completed_at: datetime | None
    audio_url: str | None = Field(
        description="Same-origin, authenticated, supports HTTP Range (for <audio>)."
    )

    @classmethod
    def from_record(cls, record: VoiceNoteRecord) -> "VoiceNote":
        ready = record.status == MediaStatus.READY.value
        return cls(
            id=record.id,
            garment_id=record.garment_id,
            status=MediaStatus(record.status),
            error_code=record.error_code,
            content_type=record.content_type,
            codec=record.codec,
            size_bytes=record.size_bytes,
            sha256=record.sha256,
            duration_ms=record.duration_ms,
            recorded_at=record.recorded_at,
            created_at=record.created_at,
            completed_at=record.completed_at,
            audio_url=f"/api/v1/voice-notes/{record.id}/audio" if ready else None,
        )
