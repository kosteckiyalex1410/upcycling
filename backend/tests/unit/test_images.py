"""Image verification and display-copy rendering (no network, no database)."""

import io
import uuid

import pytest
from PIL import Image

from app.domain.media import RejectionReason, all_keys, original_key, staging_key
from app.infrastructure.images import (
    PREVIEW_MAX_SIDE,
    THUMBNAIL_MAX_SIDE,
    ImageRejected,
    ProcessedImage,
    process_image,
    sniff_content_type,
)
from tests.media_helpers import HEIC_BYTES, make_jpeg, make_png_rgba

MAX_PIXELS = 100_000_000


def _process(data: bytes, max_pixels: int = MAX_PIXELS) -> ProcessedImage:
    return process_image(io.BytesIO(data), max_pixels=max_pixels)


@pytest.mark.parametrize(
    ("head", "expected"),
    [
        (b"\xff\xd8\xff\xe0" + b"\x00" * 8, "image/jpeg"),
        (b"\x89PNG\r\n\x1a\n" + b"\x00" * 4, "image/png"),
        (b"\x00\x00\x00\x18ftypheic", "image/heic"),
        (b"\x00\x00\x00\x18ftypheix", "image/heic"),
        (b"\x00\x00\x00\x18ftypmif1", "image/heif"),
        (b"\x00\x00\x00\x18ftypavif", None),  # AVIF is not accepted
        (b"\x00\x00\x00\x18ftypisom", None),  # MP4 video
        (b"GIF89a", None),
        (b"<svg", None),
        (b"", None),
    ],
)
def test_sniff_content_type(head: bytes, expected: str | None) -> None:
    assert sniff_content_type(head) == expected


def test_jpeg_orientation_is_applied_to_dimensions_and_copies() -> None:
    result = _process(make_jpeg((64, 48), orientation=6))
    assert result.content_type == "image/jpeg"
    assert (result.width, result.height) == (48, 64)
    assert result.exif_orientation == 6
    for jpeg in (result.preview_jpeg, result.thumbnail_jpeg):
        image = Image.open(io.BytesIO(jpeg))
        assert image.size == (48, 64)
        assert len(image.getexif()) == 0


def test_large_images_are_downscaled_for_display() -> None:
    result = _process(make_jpeg((2400, 1200)))
    assert (result.width, result.height) == (2400, 1200)
    assert Image.open(io.BytesIO(result.preview_jpeg)).size == (PREVIEW_MAX_SIDE, 800)
    assert max(Image.open(io.BytesIO(result.thumbnail_jpeg)).size) == THUMBNAIL_MAX_SIDE


def test_heic_is_decoded() -> None:
    result = _process(HEIC_BYTES)
    assert result.content_type == "image/heic"
    assert (result.width, result.height) == (96, 64)
    assert Image.open(io.BytesIO(result.preview_jpeg)).format == "JPEG"


def test_transparent_png_is_flattened_onto_white() -> None:
    result = _process(make_png_rgba())
    image = Image.open(io.BytesIO(result.thumbnail_jpeg)).convert("RGB")
    red, green, blue = image.getpixel((5, 5))  # type: ignore[misc]
    assert red > 100 and blue > 100 and green > 150  # translucent green over white


@pytest.mark.parametrize(
    ("data", "reason"),
    [
        (b"not an image at all", RejectionReason.UNSUPPORTED_MEDIA_TYPE),
        (make_jpeg()[:150], RejectionReason.INVALID_IMAGE),
        (b"\xff\xd8\xff\xe0" + b"\x00" * 100, RejectionReason.INVALID_IMAGE),
        # PNG signature followed by JPEG data: magic and decoded format disagree.
        (b"\x89PNG\r\n\x1a\n" + make_jpeg(), RejectionReason.INVALID_IMAGE),
    ],
)
def test_invalid_inputs_are_rejected(data: bytes, reason: RejectionReason) -> None:
    with pytest.raises(ImageRejected) as error:
        _process(data)
    assert error.value.reason == reason


def test_pixel_limit_is_checked_before_decoding() -> None:
    with pytest.raises(ImageRejected) as error:
        _process(make_jpeg((100, 100)), max_pixels=9_999)
    assert error.value.reason == RejectionReason.IMAGE_TOO_LARGE


def test_storage_keys_contain_only_ids() -> None:
    garment, media = uuid.uuid4(), uuid.uuid4()
    assert staging_key(media) == f"uploads/{media}"
    assert original_key(garment, media) == f"originals/{garment}/{media}"
    assert len(set(all_keys(garment, media))) == 4
