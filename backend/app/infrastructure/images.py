"""Verifies uploaded image bytes and renders display copies. CPU-bound; call off the event loop.

The original file is only read here. Previews and thumbnails are new JPEG files with the
orientation applied and all metadata (EXIF, GPS, XMP, ICC) dropped.
"""

import io
from dataclasses import dataclass
from typing import BinaryIO

import pi_heif
from PIL import Image, ImageOps, UnidentifiedImageError

from app.domain.media import RejectionReason

pi_heif.register_heif_opener()

PREVIEW_MAX_SIDE = 1600
THUMBNAIL_MAX_SIDE = 400
_JPEG_QUALITY = 85
_EXIF_ORIENTATION_TAG = 0x0112

# HEIF `ftyp` major brands for still images (HEVC-coded). AVIF and other ISO-BMFF
# formats are not accepted.
_HEIC_BRANDS = frozenset({b"heic", b"heix", b"heim", b"heis"})
_HEIF_BRANDS = frozenset({b"mif1", b"msf1", b"hevc", b"hevx"})
_PIL_FORMAT_TO_TYPE = {"JPEG": "image/jpeg", "PNG": "image/png", "HEIF": None}


class ImageRejected(Exception):
    def __init__(self, reason: RejectionReason) -> None:
        super().__init__(reason.value)
        self.reason = reason


@dataclass(frozen=True, slots=True)
class ProcessedImage:
    content_type: str  # detected from the bytes
    width: int  # as displayed, i.e. after applying the EXIF orientation
    height: int
    exif_orientation: int | None  # raw tag of the original, kept for annotation geometry
    preview_jpeg: bytes
    thumbnail_jpeg: bytes


def sniff_content_type(head: bytes) -> str | None:
    """Content type from magic bytes; None if not an accepted format."""
    if head.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if len(head) >= 12 and head[4:8] == b"ftyp":
        brand = head[8:12]
        if brand in _HEIC_BRANDS:
            return "image/heic"
        if brand in _HEIF_BRANDS:
            return "image/heif"
    return None


def _render(image: Image.Image, max_side: int) -> bytes:
    copy = image.copy()
    # Pillow re-emits some metadata from `info` by default (e.g. the JPEG comment);
    # display copies must carry none of the original's metadata.
    copy.info.clear()
    copy.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)
    out = io.BytesIO()
    copy.save(out, format="JPEG", quality=_JPEG_QUALITY, optimize=True)
    return out.getvalue()


def _to_rgb(image: Image.Image) -> Image.Image:
    if image.mode in {"RGBA", "LA"} or (image.mode == "P" and "transparency" in image.info):
        rgba = image.convert("RGBA")
        background = Image.new("RGB", rgba.size, (255, 255, 255))
        background.paste(rgba, mask=rgba.getchannel("A"))
        return background
    return image.convert("RGB")


def process_image(source: BinaryIO, *, max_pixels: int) -> ProcessedImage:
    """Raises `ImageRejected` for anything that is not a decodable JPEG, PNG or HEIC/HEIF."""
    source.seek(0)
    content_type = sniff_content_type(source.read(32))
    if content_type is None:
        raise ImageRejected(RejectionReason.UNSUPPORTED_MEDIA_TYPE)
    source.seek(0)
    try:
        with Image.open(source) as image:
            expected = _PIL_FORMAT_TO_TYPE.get(image.format or "", "")
            if expected == "" or (expected is not None and expected != content_type):
                raise ImageRejected(RejectionReason.UNSUPPORTED_MEDIA_TYPE)
            width, height = image.size
            if width * height > max_pixels:
                raise ImageRejected(RejectionReason.IMAGE_TOO_LARGE)
            raw_orientation = image.getexif().get(_EXIF_ORIENTATION_TAG)
            image.load()  # full decode: catches truncated or corrupt files
            oriented = _to_rgb(ImageOps.exif_transpose(image))
    except ImageRejected:
        raise
    except (UnidentifiedImageError, Image.DecompressionBombError, OSError, ValueError) as exc:
        raise ImageRejected(RejectionReason.INVALID_IMAGE) from exc
    return ProcessedImage(
        content_type=content_type,
        width=oriented.width,
        height=oriented.height,
        exif_orientation=raw_orientation if isinstance(raw_orientation, int) else None,
        preview_jpeg=_render(oriented, PREVIEW_MAX_SIDE),
        thumbnail_jpeg=_render(oriented, THUMBNAIL_MAX_SIDE),
    )
