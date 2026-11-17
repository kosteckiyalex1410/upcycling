"""Garment projects and their photos. Every route is authenticated and owner-scoped; other
users' resources are reported as `not_found` (ADR-0006)."""

import logging
import uuid
from collections.abc import AsyncIterator
from datetime import datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Query, Request, Response, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from app.api.v1.deps import ClockDep, CurrentUser, DbDep, SettingsDep, StorageDep
from app.api.v1.voice_note_schemas import VoiceNote
from app.application.errors import NotFound
from app.application.garments import GarmentService, UploadRequest, UploadTicket
from app.application.ports import ObjectMissingError
from app.domain.media import MediaCategory, MediaStatus
from app.infrastructure.db.garments import GarmentListItem
from app.infrastructure.db.models import GarmentRecord, MediaAssetRecord, VoiceNoteRecord

logger = logging.getLogger(__name__)
router = APIRouter(tags=["garments"])

_MEDIA_PATH = "/api/v1/media/{id}/{variant}"


def _media_url(media_id: uuid.UUID, variant: str) -> str:
    return _MEDIA_PATH.format(id=media_id, variant=variant)


# Schemas ----------------------------------------------------------------------------------

Title = Annotated[str | None, Field(max_length=120)]
Notes = Annotated[str | None, Field(max_length=4000)]


class MediaAsset(BaseModel):
    id: uuid.UUID
    garment_id: uuid.UUID
    category: MediaCategory | None = Field(description="Null until the expert assigns one.")
    status: MediaStatus
    error_code: str | None = Field(description="Set when `status` is `rejected`.")
    original_filename: str | None
    content_type: str | None = Field(description="Detected from the bytes; set when ready.")
    size_bytes: int | None
    sha256: str | None = Field(description="Hex SHA-256 of the stored original.")
    width: int | None = Field(description="Displayed width (EXIF orientation applied).")
    height: int | None
    created_at: datetime
    completed_at: datetime | None
    thumbnail_url: str | None = Field(description="Same-origin, authenticated; ~400 px JPEG.")
    preview_url: str | None = Field(description="Same-origin, authenticated; ~1600 px JPEG.")
    original_url: str | None = Field(description="Original bytes as uploaded (download).")

    @classmethod
    def from_record(cls, record: MediaAssetRecord) -> "MediaAsset":
        ready = record.status == MediaStatus.READY.value
        return cls(
            id=record.id,
            garment_id=record.garment_id,
            category=MediaCategory(record.category) if record.category else None,
            status=MediaStatus(record.status),
            error_code=record.error_code,
            original_filename=record.original_filename,
            content_type=record.content_type,
            size_bytes=record.size_bytes,
            sha256=record.sha256,
            width=record.width,
            height=record.height,
            created_at=record.created_at,
            completed_at=record.completed_at,
            thumbnail_url=_media_url(record.id, "thumbnail") if ready else None,
            preview_url=_media_url(record.id, "preview") if ready else None,
            original_url=_media_url(record.id, "original") if ready else None,
        )


class GarmentSummary(BaseModel):
    id: uuid.UUID
    title: str | None
    created_at: datetime
    updated_at: datetime
    photo_count: int = Field(description="Ready photos.")
    cover_thumbnail_url: str | None

    @classmethod
    def from_item(cls, item: GarmentListItem) -> "GarmentSummary":
        g = item.garment
        return cls(
            id=g.id,
            title=g.title,
            created_at=g.created_at,
            updated_at=g.updated_at,
            photo_count=item.photo_count,
            cover_thumbnail_url=(
                _media_url(item.cover_media_id, "thumbnail") if item.cover_media_id else None
            ),
        )


class Garment(BaseModel):
    id: uuid.UUID
    title: str | None
    notes: str | None
    created_at: datetime
    updated_at: datetime
    media: list[MediaAsset] = Field(description="Photos including pending and rejected ones.")
    voice_notes: list[VoiceNote] = Field(
        description="Voice recordings including pending and rejected ones."
    )

    @classmethod
    def from_records(
        cls,
        garment: GarmentRecord,
        media: list[MediaAssetRecord],
        voice_notes: list[VoiceNoteRecord],
    ) -> "Garment":
        return cls(
            id=garment.id,
            title=garment.title,
            notes=garment.notes,
            created_at=garment.created_at,
            updated_at=garment.updated_at,
            media=[MediaAsset.from_record(m) for m in media],
            voice_notes=[VoiceNote.from_record(n) for n in voice_notes],
        )


class GarmentPage(BaseModel):
    items: list[GarmentSummary]
    next_cursor: str | None = Field(description="Pass as `cursor` for the next page.")


class CreateGarmentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    client_request_id: uuid.UUID = Field(description="Idempotency key; retries reuse it.")
    title: Title = None
    notes: Notes = None


class UpdateGarmentRequest(BaseModel):
    """Only fields present are changed; `null` clears a field."""

    model_config = ConfigDict(extra="forbid")

    title: Title = None
    notes: Notes = None


class CreateUploadRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    client_upload_id: uuid.UUID = Field(description="Idempotency key; retries reuse it.")
    category: MediaCategory | None = Field(default=None, description="Optional; set later.")
    content_type: str = Field(max_length=100, description="image/jpeg, image/png, image/heic…")
    size_bytes: int = Field(gt=0)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$", description="Lowercase hex SHA-256.")
    filename: str | None = Field(default=None, max_length=255)


class PresignedUpload(BaseModel):
    url: str = Field(description="Short-lived URL on the object storage origin.")
    method: Literal["PUT"] = "PUT"
    headers: dict[str, str] = Field(description="Send exactly these headers with the body.")
    expires_at: datetime

    @classmethod
    def from_ticket(cls, ticket: UploadTicket) -> "PresignedUpload":
        return cls(url=ticket.url, headers=ticket.headers, expires_at=ticket.expires_at)


class UploadTicketResponse(BaseModel):
    media: MediaAsset
    upload: PresignedUpload | None = Field(description="Null once the photo is not pending.")


class CompleteUploadRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    media_id: uuid.UUID


class UpdateMediaRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    category: MediaCategory | None = Field(description="`null` removes the category.")


def _normalize_content_type(value: str) -> str:
    value = value.split(";", 1)[0].strip().lower()
    return "image/jpeg" if value == "image/jpg" else value


# Routes -----------------------------------------------------------------------------------


def _service(
    db: DbDep, settings: SettingsDep, clock: ClockDep, storage: StorageDep
) -> GarmentService:
    return GarmentService(db, settings, clock, storage)


@router.post(
    "/garments",
    response_model=Garment,
    status_code=status.HTTP_201_CREATED,
    responses={200: {"model": Garment, "description": "Replay of an earlier create."}},
)
async def create_garment(
    body: CreateGarmentRequest,
    response: Response,
    user: CurrentUser,
    db: DbDep,
    settings: SettingsDep,
    clock: ClockDep,
    storage: StorageDep,
) -> Garment:
    service = _service(db, settings, clock, storage)
    garment, created = await service.create(
        user.id, client_request_id=body.client_request_id, title=body.title, notes=body.notes
    )
    if not created:
        response.status_code = status.HTTP_200_OK
    _, media, notes = await service.get(user.id, garment.id)
    return Garment.from_records(garment, media, notes)


@router.get("/garments", response_model=GarmentPage)
async def list_garments(
    user: CurrentUser,
    db: DbDep,
    settings: SettingsDep,
    clock: ClockDep,
    storage: StorageDep,
    cursor: uuid.UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 30,
) -> GarmentPage:
    items = await _service(db, settings, clock, storage).list_page(
        user.id, before_id=cursor, limit=limit + 1
    )
    page = items[:limit]
    return GarmentPage(
        items=[GarmentSummary.from_item(item) for item in page],
        next_cursor=str(page[-1].garment.id) if len(items) > limit else None,
    )


@router.get("/garments/{garment_id}", response_model=Garment)
async def get_garment(
    garment_id: uuid.UUID,
    user: CurrentUser,
    db: DbDep,
    settings: SettingsDep,
    clock: ClockDep,
    storage: StorageDep,
) -> Garment:
    garment, media, notes = await _service(db, settings, clock, storage).get(user.id, garment_id)
    return Garment.from_records(garment, media, notes)


@router.patch("/garments/{garment_id}", response_model=Garment)
async def update_garment(
    garment_id: uuid.UUID,
    body: UpdateGarmentRequest,
    user: CurrentUser,
    db: DbDep,
    settings: SettingsDep,
    clock: ClockDep,
    storage: StorageDep,
) -> Garment:
    service = _service(db, settings, clock, storage)
    changes = {name: getattr(body, name) for name in body.model_fields_set}
    garment = await service.update(user.id, garment_id, changes)
    _, media, notes = await service.get(user.id, garment.id)
    return Garment.from_records(garment, media, notes)


@router.delete("/garments/{garment_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_garment(
    garment_id: uuid.UUID,
    user: CurrentUser,
    db: DbDep,
    settings: SettingsDep,
    clock: ClockDep,
    storage: StorageDep,
) -> None:
    await _service(db, settings, clock, storage).delete(user.id, garment_id)


@router.post("/garments/{garment_id}/media/uploads", response_model=UploadTicketResponse)
async def create_media_upload(
    garment_id: uuid.UUID,
    body: CreateUploadRequest,
    user: CurrentUser,
    db: DbDep,
    settings: SettingsDep,
    clock: ClockDep,
    storage: StorageDep,
) -> UploadTicketResponse:
    """Register a photo and get a presigned PUT for its bytes. Calling again with the same
    `client_upload_id` returns the same photo with a fresh URL while it is pending."""
    media, ticket = await _service(db, settings, clock, storage).request_upload(
        user.id,
        garment_id,
        UploadRequest(
            client_upload_id=body.client_upload_id,
            category=body.category,
            content_type=_normalize_content_type(body.content_type),
            size_bytes=body.size_bytes,
            sha256=body.sha256,
            filename=body.filename,
        ),
    )
    return UploadTicketResponse(
        media=MediaAsset.from_record(media),
        upload=PresignedUpload.from_ticket(ticket) if ticket else None,
    )


@router.post("/garments/{garment_id}/media/complete", response_model=MediaAsset)
async def complete_media_upload(
    garment_id: uuid.UUID,
    body: CompleteUploadRequest,
    user: CurrentUser,
    db: DbDep,
    settings: SettingsDep,
    clock: ClockDep,
    storage: StorageDep,
) -> MediaAsset:
    """Verify the uploaded bytes and register the photo. Returns it as `ready` or `rejected`
    (with `error_code`); `upload_incomplete` (409) if the bytes have not arrived yet.
    Safe to repeat."""
    media = await _service(db, settings, clock, storage).complete_upload(
        user.id, garment_id, body.media_id
    )
    return MediaAsset.from_record(media)


@router.patch("/media/{media_id}", response_model=MediaAsset)
async def update_media(
    media_id: uuid.UUID,
    body: UpdateMediaRequest,
    user: CurrentUser,
    db: DbDep,
    settings: SettingsDep,
    clock: ClockDep,
    storage: StorageDep,
) -> MediaAsset:
    media = await _service(db, settings, clock, storage).set_category(
        user.id, media_id, body.category
    )
    return MediaAsset.from_record(media)


@router.delete("/media/{media_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_media(
    media_id: uuid.UUID,
    user: CurrentUser,
    db: DbDep,
    settings: SettingsDep,
    clock: ClockDep,
    storage: StorageDep,
) -> None:
    await _service(db, settings, clock, storage).delete_media(user.id, media_id)


# Media bytes ------------------------------------------------------------------------------

_EXTENSIONS = {"image/jpeg": "jpg", "image/png": "png", "image/heic": "heic", "image/heif": "heif"}
_BINARY_RESPONSE: dict[int | str, dict[str, Any]] = {
    200: {"content": {"image/*": {}}, "description": "Image bytes."},
    304: {"description": "Not modified (matching `If-None-Match`)."},
}


def _media_headers(etag: str) -> dict[str, str]:
    # `no-cache`: the browser may keep a copy but must revalidate, so every view re-checks
    # the session and ownership (cheap 304s via ETag). The sandbox CSP neutralises any
    # active content if a response is ever opened as a document.
    return {
        "ETag": etag,
        "Cache-Control": "private, no-cache",
        "Content-Security-Policy": "default-src 'none'; sandbox",
        "Cross-Origin-Resource-Policy": "same-origin",
    }


async def _read(storage: StorageDep, key: str | None) -> bytes:
    try:
        return await storage.read_bytes(key or "")
    except ObjectMissingError as exc:
        logger.error("media_object_missing", extra={"fields": {"key": key}})
        raise NotFound from exc


async def _open(storage: StorageDep, key: str | None) -> AsyncIterator[bytes]:
    try:
        return await storage.open_stream(key or "")
    except ObjectMissingError as exc:
        logger.error("media_object_missing", extra={"fields": {"key": key}})
        raise NotFound from exc


def _not_modified(request: Request, etag: str) -> Response | None:
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=status.HTTP_304_NOT_MODIFIED, headers=_media_headers(etag))
    return None


async def _display_copy(
    variant: Literal["thumbnail", "preview"],
    media_id: uuid.UUID,
    request: Request,
    service: GarmentService,
    storage: StorageDep,
    owner_id: uuid.UUID,
) -> Response:
    media = await service.get_ready_media(owner_id, media_id)
    etag = f'"{variant}-{media.sha256}"'
    if cached := _not_modified(request, etag):
        return cached
    key = media.thumbnail_key if variant == "thumbnail" else media.preview_key
    data = await _read(storage, key)
    return Response(data, media_type="image/jpeg", headers=_media_headers(etag))


@router.get("/media/{media_id}/thumbnail", response_class=Response, responses=_BINARY_RESPONSE)
async def get_media_thumbnail(
    media_id: uuid.UUID,
    request: Request,
    user: CurrentUser,
    db: DbDep,
    settings: SettingsDep,
    clock: ClockDep,
    storage: StorageDep,
) -> Response:
    """~400 px JPEG, orientation applied, all metadata removed."""
    service = _service(db, settings, clock, storage)
    return await _display_copy("thumbnail", media_id, request, service, storage, user.id)


@router.get("/media/{media_id}/preview", response_class=Response, responses=_BINARY_RESPONSE)
async def get_media_preview(
    media_id: uuid.UUID,
    request: Request,
    user: CurrentUser,
    db: DbDep,
    settings: SettingsDep,
    clock: ClockDep,
    storage: StorageDep,
) -> Response:
    """~1600 px JPEG, orientation applied, all metadata removed."""
    service = _service(db, settings, clock, storage)
    return await _display_copy("preview", media_id, request, service, storage, user.id)


@router.get(
    "/media/{media_id}/original",
    response_class=StreamingResponse,
    responses=_BINARY_RESPONSE,
)
async def get_media_original(
    media_id: uuid.UUID,
    request: Request,
    user: CurrentUser,
    db: DbDep,
    settings: SettingsDep,
    clock: ClockDep,
    storage: StorageDep,
) -> Response:
    """Original bytes exactly as uploaded (may contain EXIF/GPS metadata), as a download."""
    media = await _service(db, settings, clock, storage).get_ready_media(user.id, media_id)
    etag = f'"{media.sha256}"'
    if cached := _not_modified(request, etag):
        return cached
    content_type = media.content_type or "application/octet-stream"
    chunks = await _open(storage, media.original_key)
    headers = _media_headers(etag) | {
        "Content-Length": str(media.size_bytes),
        "Content-Disposition": (
            f'attachment; filename="photo-{media.id}.{_EXTENSIONS.get(content_type, "bin")}"'
        ),
    }
    return StreamingResponse(chunks, media_type=content_type, headers=headers)
