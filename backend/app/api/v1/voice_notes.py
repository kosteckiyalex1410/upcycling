"""Voice notes of a garment (ADR-0007). Authenticated and owner-scoped like photos; other
users' recordings are `not_found`. Audio is only served through this API, never from a
storage URL."""

import logging
import re
import uuid
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Request, Response, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from app.api.v1.deps import ClockDep, CurrentUser, DbDep, SettingsDep, StorageDep
from app.api.v1.garments import PresignedUpload, _media_headers, _not_modified
from app.api.v1.voice_note_schemas import VoiceNote
from app.application.errors import NotFound
from app.application.ports import ObjectMissingError
from app.application.voice_notes import VoiceNoteService, VoiceNoteUploadRequest

logger = logging.getLogger(__name__)
router = APIRouter(tags=["voice-notes"])


class CreateVoiceNoteUploadRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    client_upload_id: uuid.UUID = Field(description="Idempotency key; retries reuse it.")
    content_type: str = Field(
        max_length=100, description="`MediaRecorder.mimeType`: audio/mp4 or audio/webm…"
    )
    size_bytes: int = Field(gt=0)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$", description="Lowercase hex SHA-256.")
    duration_ms: Annotated[int | None, Field(ge=0)] = Field(
        default=None, description="Duration measured while recording (informational)."
    )
    recorded_at: datetime | None = Field(default=None, description="When recording started.")


class VoiceNoteUploadTicket(BaseModel):
    voice_note: VoiceNote
    upload: PresignedUpload | None = Field(description="Null once the note is not pending.")


class CompleteVoiceNoteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    voice_note_id: uuid.UUID


def _normalize_audio_type(value: str) -> str:
    # "audio/mp4; codecs=mp4a.40.2" -> "audio/mp4"; Safari has also reported audio/x-m4a.
    value = value.split(";", 1)[0].strip().lower()
    return "audio/mp4" if value in {"audio/x-m4a", "audio/m4a", "audio/aac"} else value


def _service(
    db: DbDep, settings: SettingsDep, clock: ClockDep, storage: StorageDep
) -> VoiceNoteService:
    return VoiceNoteService(db, settings, clock, storage)


@router.post("/garments/{garment_id}/voice-notes/uploads", response_model=VoiceNoteUploadTicket)
async def create_voice_note_upload(
    garment_id: uuid.UUID,
    body: CreateVoiceNoteUploadRequest,
    user: CurrentUser,
    db: DbDep,
    settings: SettingsDep,
    clock: ClockDep,
    storage: StorageDep,
) -> VoiceNoteUploadTicket:
    """Register a recording and get a presigned PUT for its bytes. Calling again with the
    same `client_upload_id` returns the same note with a fresh URL while it is pending."""
    note, ticket = await _service(db, settings, clock, storage).request_upload(
        user.id,
        garment_id,
        VoiceNoteUploadRequest(
            client_upload_id=body.client_upload_id,
            content_type=_normalize_audio_type(body.content_type),
            size_bytes=body.size_bytes,
            sha256=body.sha256,
            duration_ms=body.duration_ms,
            recorded_at=body.recorded_at,
        ),
    )
    return VoiceNoteUploadTicket(
        voice_note=VoiceNote.from_record(note),
        upload=PresignedUpload.from_ticket(ticket) if ticket else None,
    )


@router.post("/garments/{garment_id}/voice-notes/complete", response_model=VoiceNote)
async def complete_voice_note_upload(
    garment_id: uuid.UUID,
    body: CompleteVoiceNoteRequest,
    user: CurrentUser,
    db: DbDep,
    settings: SettingsDep,
    clock: ClockDep,
    storage: StorageDep,
) -> VoiceNote:
    """Verify the uploaded recording (size, SHA-256, container, codec, real duration).
    Returns it as `ready` or `rejected` (with `error_code`); `upload_incomplete` (409) if
    the bytes have not arrived yet. Safe to repeat."""
    note = await _service(db, settings, clock, storage).complete_upload(
        user.id, garment_id, body.voice_note_id
    )
    return VoiceNote.from_record(note)


@router.delete("/voice-notes/{voice_note_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_voice_note(
    voice_note_id: uuid.UUID,
    user: CurrentUser,
    db: DbDep,
    settings: SettingsDep,
    clock: ClockDep,
    storage: StorageDep,
) -> None:
    """Permanently delete the recording and its metadata."""
    await _service(db, settings, clock, storage).delete(user.id, voice_note_id)


_RANGE = re.compile(r"^bytes=(\d*)-(\d*)$")
_AUDIO_RESPONSE: dict[int | str, dict[str, Any]] = {
    200: {"content": {"audio/*": {}}, "description": "Audio bytes."},
    206: {"description": "Requested byte range."},
    304: {"description": "Not modified (matching `If-None-Match`)."},
    416: {"description": "Range not satisfiable."},
}


def _byte_range(header: str | None, size: int) -> tuple[int, int] | None:
    """Inclusive (start, end) for a single `bytes=` range; None for the whole file.
    Raises ValueError if unsatisfiable. Multiple ranges are answered with the whole file."""
    if not header or "," in header:
        return None
    match = _RANGE.match(header.strip())
    if not match or (not match[1] and not match[2]):
        return None
    if not match[1]:  # suffix: last N bytes
        length = int(match[2])
        if length == 0:
            raise ValueError("empty suffix range")
        return max(size - length, 0), size - 1
    start = int(match[1])
    end = min(int(match[2]), size - 1) if match[2] else size - 1
    if start >= size or end < start:
        raise ValueError("range outside the file")
    return start, end


@router.get(
    "/voice-notes/{voice_note_id}/audio",
    response_class=StreamingResponse,
    responses=_AUDIO_RESPONSE,
)
async def get_voice_note_audio(
    voice_note_id: uuid.UUID,
    request: Request,
    user: CurrentUser,
    db: DbDep,
    settings: SettingsDep,
    clock: ClockDep,
    storage: StorageDep,
) -> Response:
    """The original recording, for playback. Supports a single HTTP byte range, which
    Safari requires for `<audio>`."""
    note = await _service(db, settings, clock, storage).get_ready(user.id, voice_note_id)
    etag = f'"{note.sha256}"'
    if cached := _not_modified(request, etag):
        return cached
    size = note.size_bytes or 0
    headers = _media_headers(etag) | {"Accept-Ranges": "bytes"}
    try:
        byte_range = _byte_range(request.headers.get("range"), size)
    except ValueError:
        return Response(
            status_code=status.HTTP_416_RANGE_NOT_SATISFIABLE,
            headers=headers | {"Content-Range": f"bytes */{size}"},
        )
    try:
        chunks = await storage.open_stream(note.audio_key or "", byte_range=byte_range)
    except ObjectMissingError as exc:
        logger.error("voice_note_object_missing", extra={"fields": {"voice_note_id": note.id}})
        raise NotFound from exc
    media_type = note.content_type or "application/octet-stream"
    if byte_range is None:
        return StreamingResponse(
            chunks, media_type=media_type, headers=headers | {"Content-Length": str(size)}
        )
    start, end = byte_range
    return StreamingResponse(
        chunks,
        status_code=status.HTTP_206_PARTIAL_CONTENT,
        media_type=media_type,
        headers=headers
        | {"Content-Range": f"bytes {start}-{end}/{size}", "Content-Length": str(end - start + 1)},
    )
