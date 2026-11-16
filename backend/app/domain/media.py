"""Garment photos: categories, lifecycle and object-storage layout (ADR-0006).

Originals are evidence: once a photo is `ready`, its stored bytes and content fields never
change. Storage keys contain only UUIDs, never filenames, emails or other user data.
"""

import uuid
from enum import StrEnum


class MediaCategory(StrEnum):
    """What the photo shows. Stable, language-neutral values (persisted and in the API)."""

    FRONT = "front"
    BACK = "back"
    DETAIL = "detail"
    FABRIC = "fabric"
    DEFECT = "defect"
    LABEL = "label"


class MediaStatus(StrEnum):
    PENDING = "pending"  # upload ticket issued; bytes not yet verified
    READY = "ready"  # verified original and derived previews stored
    REJECTED = "rejected"  # verification failed; see `error_code`; bytes deleted


class RejectionReason(StrEnum):
    UNSUPPORTED_MEDIA_TYPE = "unsupported_media_type"
    INVALID_IMAGE = "invalid_image"
    IMAGE_TOO_LARGE = "image_too_large"
    UPLOAD_TOO_LARGE = "upload_too_large"
    CHECKSUM_MISMATCH = "checksum_mismatch"


# Declared types the client may upload. The stored `content_type` is always the type
# detected from the bytes, never the declared one.
SUPPORTED_CONTENT_TYPES = frozenset({"image/jpeg", "image/png", "image/heic", "image/heif"})


def staging_key(media_id: uuid.UUID) -> str:
    """Where the browser uploads (presigned PUT). Never served; deleted after verification."""
    return f"uploads/{media_id}"


def original_key(garment_id: uuid.UUID, media_id: uuid.UUID) -> str:
    """Verified original, written only by the server, never overwritten."""
    return f"originals/{garment_id}/{media_id}"


def preview_key(garment_id: uuid.UUID, media_id: uuid.UUID) -> str:
    return f"derived/{garment_id}/{media_id}/preview.jpg"


def thumbnail_key(garment_id: uuid.UUID, media_id: uuid.UUID) -> str:
    return f"derived/{garment_id}/{media_id}/thumbnail.jpg"


def all_keys(garment_id: uuid.UUID, media_id: uuid.UUID) -> list[str]:
    """Every object a photo may own, for deletion."""
    return [
        staging_key(media_id),
        original_key(garment_id, media_id),
        preview_key(garment_id, media_id),
        thumbnail_key(garment_id, media_id),
    ]
