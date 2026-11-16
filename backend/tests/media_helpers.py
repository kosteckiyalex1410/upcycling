"""Test image factories and a client-side implementation of the upload protocol."""

import hashlib
import io
import uuid
from pathlib import Path
from typing import Any

import httpx
from PIL import Image

FIXTURES = Path(__file__).parent / "fixtures"
HEIC_BYTES = (FIXTURES / "sample.heic").read_bytes()


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def make_jpeg(size: tuple[int, int] = (64, 48), *, orientation: int | None = None) -> bytes:
    image = Image.new("RGB", size, (200, 30, 30))
    image.paste((20, 20, 220), (0, 0, size[0] // 2, size[1]))
    out = io.BytesIO()
    exif = Image.Exif()
    if orientation is not None:
        exif[0x0112] = orientation
    # A GPS tag stands in for location metadata that must survive in the original only.
    exif[0x8825] = {1: "N", 2: (50.0, 27.0, 0.0)}
    image.save(out, format="JPEG", exif=exif.tobytes())
    return out.getvalue()


def make_png_rgba(size: tuple[int, int] = (40, 30)) -> bytes:
    out = io.BytesIO()
    Image.new("RGBA", size, (0, 128, 0, 100)).save(out, format="PNG")
    return out.getvalue()


def upload_body(
    data: bytes,
    *,
    content_type: str = "image/jpeg",
    category: str = "front",
    client_upload_id: uuid.UUID | None = None,
    filename: str | None = "IMG_0001.JPG",
) -> dict[str, Any]:
    return {
        "client_upload_id": str(client_upload_id or uuid.uuid4()),
        "category": category,
        "content_type": content_type,
        "size_bytes": len(data),
        "sha256": sha256_hex(data),
        "filename": filename,
    }


async def put_to_storage(upload: dict[str, Any], data: bytes) -> httpx.Response:
    """What the browser does: a direct PUT to object storage with the given headers."""
    async with httpx.AsyncClient() as storage_client:
        return await storage_client.request(
            upload["method"], upload["url"], content=data, headers=upload["headers"]
        )


async def create_garment(client: httpx.AsyncClient, title: str | None = None) -> dict[str, Any]:
    response = await client.post(
        "/api/v1/garments", json={"client_request_id": str(uuid.uuid4()), "title": title}
    )
    assert response.status_code == 201, response.text
    body: dict[str, Any] = response.json()
    return body


async def upload_photo(
    client: httpx.AsyncClient,
    garment_id: str,
    data: bytes,
    *,
    content_type: str = "image/jpeg",
    category: str = "front",
) -> dict[str, Any]:
    """Full protocol: register, PUT to storage, complete. Returns the final media JSON."""
    ticket = await client.post(
        f"/api/v1/garments/{garment_id}/media/uploads",
        json=upload_body(data, content_type=content_type, category=category),
    )
    assert ticket.status_code == 200, ticket.text
    stored = await put_to_storage(ticket.json()["upload"], data)
    assert stored.status_code == 200, stored.text
    done = await client.post(
        f"/api/v1/garments/{garment_id}/media/complete",
        json={"media_id": ticket.json()["media"]["id"]},
    )
    assert done.status_code == 200, done.text
    media: dict[str, Any] = done.json()
    return media
