"""Photo upload protocol against real PostgreSQL and S3-compatible storage (ADR-0006)."""

import asyncio
import io
import logging
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from PIL import Image

from app.application.garments import StorageSweeper
from app.config import Settings
from app.domain.media import original_key, staging_key
from app.domain.users import User
from app.infrastructure.storage import S3ObjectStorage
from app.main import create_app
from tests.conftest import FakeClock, RecordingEmailSender, login, make_client
from tests.media_helpers import (
    HEIC_BYTES,
    create_garment,
    make_jpeg,
    make_png_rgba,
    put_to_storage,
    sha256_hex,
    upload_body,
    upload_photo,
)


@pytest.fixture
async def expert(
    client: httpx.AsyncClient, email_sender: RecordingEmailSender, user: User
) -> httpx.AsyncClient:
    await login(client, email_sender)
    return client


@pytest.fixture
async def garment(expert: httpx.AsyncClient) -> dict[str, Any]:
    return await create_garment(expert, "Jacket")


def storage_of(app: FastAPI) -> S3ObjectStorage:
    storage: S3ObjectStorage = app.state.storage
    return storage


async def keys(app: FastAPI) -> set[str]:
    return {obj.key for obj in await storage_of(app).list_objects("")}


def uploads_url(garment: dict[str, Any]) -> str:
    return f"/api/v1/garments/{garment['id']}/media/uploads"


def complete_url(garment: dict[str, Any]) -> str:
    return f"/api/v1/garments/{garment['id']}/media/complete"


# --- Happy paths -------------------------------------------------------------------------------


async def test_jpeg_upload_preserves_original_and_strips_metadata_from_previews(
    app: FastAPI, expert: httpx.AsyncClient, garment: dict[str, Any]
) -> None:
    data = make_jpeg((64, 48), orientation=6)  # rotated 90°: displayed as 48x64
    media = await upload_photo(expert, garment["id"], data, category="label")

    assert media["status"] == "ready"
    assert media["category"] == "label"
    assert media["content_type"] == "image/jpeg"
    assert media["size_bytes"] == len(data)
    assert media["sha256"] == sha256_hex(data)
    assert (media["width"], media["height"]) == (48, 64)
    assert media["original_filename"] == "IMG_0001.JPG"

    original = await expert.get(media["original_url"])
    assert original.status_code == 200
    assert original.content == data  # byte-for-byte, EXIF/GPS included
    assert original.headers["content-type"] == "image/jpeg"
    assert original.headers["content-disposition"].startswith("attachment;")
    assert original.headers["cache-control"] == "private, no-cache"
    assert "sandbox" in original.headers["content-security-policy"]
    assert original.headers["x-content-type-options"] == "nosniff"

    for variant, max_side in (("thumbnail_url", 400), ("preview_url", 1600)):
        response = await expert.get(media[variant])
        assert response.status_code == 200
        assert response.headers["content-type"] == "image/jpeg"
        image = Image.open(io.BytesIO(response.content))
        assert image.size == (48, 64)  # orientation applied
        assert max(image.size) <= max_side
        assert len(image.getexif()) == 0  # no EXIF/GPS in display copies

    # Verified original is server-written; the staging object is gone.
    assert staging_key(uuid.UUID(media["id"])) not in await keys(app)
    assert original_key(uuid.UUID(garment["id"]), uuid.UUID(media["id"])) in await keys(app)


async def test_heic_and_png_are_accepted(
    expert: httpx.AsyncClient, garment: dict[str, Any]
) -> None:
    heic = await upload_photo(expert, garment["id"], HEIC_BYTES, content_type="image/heic")
    assert heic["status"] == "ready"
    assert heic["content_type"] == "image/heic"
    assert (heic["width"], heic["height"]) == (96, 64)
    preview = await expert.get(heic["preview_url"])
    assert Image.open(io.BytesIO(preview.content)).format == "JPEG"  # displayable everywhere

    png = await upload_photo(expert, garment["id"], make_png_rgba(), content_type="image/png")
    assert png["status"] == "ready"
    assert png["content_type"] == "image/png"


async def test_etag_revalidation_returns_304(
    expert: httpx.AsyncClient, garment: dict[str, Any]
) -> None:
    media = await upload_photo(expert, garment["id"], make_jpeg())
    first = await expert.get(media["thumbnail_url"])
    again = await expert.get(
        media["thumbnail_url"], headers={"If-None-Match": first.headers["etag"]}
    )
    assert again.status_code == 304
    assert again.content == b""


async def test_garment_detail_lists_photos_in_upload_order(
    expert: httpx.AsyncClient, garment: dict[str, Any]
) -> None:
    a = await upload_photo(expert, garment["id"], make_jpeg(), category="front")
    b = await upload_photo(expert, garment["id"], make_jpeg((30, 30)), category="defect")
    detail = (await expert.get(f"/api/v1/garments/{garment['id']}")).json()
    assert [m["id"] for m in detail["media"]] == [a["id"], b["id"]]


# --- Retries and idempotency -------------------------------------------------------------------


async def test_every_step_can_be_retried(
    expert: httpx.AsyncClient, garment: dict[str, Any]
) -> None:
    data = make_jpeg()
    body = upload_body(data)
    first = (await expert.post(uploads_url(garment), json=body)).json()
    media_id = first["media"]["id"]

    # Completing before the bytes arrive: retryable conflict, photo stays pending.
    early = await expert.post(complete_url(garment), json={"media_id": media_id})
    assert early.status_code == 409
    assert early.json()["error"]["code"] == "upload_incomplete"

    # Asking again (e.g. the URL expired) returns the same photo with a fresh ticket.
    second = (await expert.post(uploads_url(garment), json=body)).json()
    assert second["media"]["id"] == media_id
    assert second["upload"]["url"]

    assert (await put_to_storage(second["upload"], data)).status_code == 200
    assert (await put_to_storage(second["upload"], data)).status_code == 200  # re-PUT is fine
    done = await expert.post(complete_url(garment), json={"media_id": media_id})
    replay = await expert.post(complete_url(garment), json={"media_id": media_id})
    assert done.json()["status"] == replay.json()["status"] == "ready"

    after = (await expert.post(uploads_url(garment), json=body)).json()
    assert after["media"]["status"] == "ready"
    assert after["upload"] is None  # nothing more to upload

    detail = (await expert.get(f"/api/v1/garments/{garment['id']}")).json()
    assert len(detail["media"]) == 1


async def test_reusing_an_upload_key_with_different_content_conflicts(
    expert: httpx.AsyncClient, garment: dict[str, Any]
) -> None:
    key = uuid.uuid4()
    await expert.post(uploads_url(garment), json=upload_body(make_jpeg(), client_upload_id=key))
    other = upload_body(make_jpeg((10, 10)), client_upload_id=key)
    response = await expert.post(uploads_url(garment), json=other)
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "idempotency_conflict"


# --- Storage-enforced constraints on presigned uploads -----------------------------------------


async def test_presigned_url_constrains_type_length_and_content(
    expert: httpx.AsyncClient, garment: dict[str, Any]
) -> None:
    data = make_jpeg()
    upload = (await expert.post(uploads_url(garment), json=upload_body(data))).json()["upload"]
    assert upload["method"] == "PUT"
    assert "uploads/" in upload["url"]
    assert set(upload["headers"]) == {"Content-Type", "x-amz-checksum-sha256"}
    assert "upcycling-dev-storage-secret" not in upload["url"]

    tampered = bytearray(data)
    tampered[-3] ^= 0xFF
    assert (await put_to_storage(upload, bytes(tampered))).status_code >= 400
    assert (await put_to_storage(upload, data + b"extra")).status_code >= 400
    other_type = {**upload, "headers": {**upload["headers"], "Content-Type": "text/html"}}
    assert (await put_to_storage(other_type, data)).status_code >= 400
    assert (await put_to_storage(upload, data)).status_code == 200


async def test_presigned_url_expires(
    expert: httpx.AsyncClient,
    garment: dict[str, Any],
    app: FastAPI,
) -> None:
    app.state.settings.upload_url_ttl_seconds = 1
    data = make_jpeg()
    upload = (await expert.post(uploads_url(garment), json=upload_body(data))).json()["upload"]
    await asyncio.sleep(2.1)
    assert (await put_to_storage(upload, data)).status_code == 403


# --- Content validation ------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("declared", "content_type", "reason"),
    [
        (b"<html><script>alert(1)</script></html>", "image/jpeg", "unsupported_media_type"),
        (b"GIF89a" + b"\x00" * 64, "image/png", "unsupported_media_type"),
        (b"<svg xmlns='http://www.w3.org/2000/svg'/>", "image/png", "unsupported_media_type"),
        (make_jpeg()[:200], "image/jpeg", "invalid_image"),  # truncated
    ],
)
async def test_non_images_are_rejected_after_upload(
    app: FastAPI,
    expert: httpx.AsyncClient,
    garment: dict[str, Any],
    declared: bytes,
    content_type: str,
    reason: str,
) -> None:
    ticket = (
        await expert.post(
            uploads_url(garment), json=upload_body(declared, content_type=content_type)
        )
    ).json()
    assert (await put_to_storage(ticket["upload"], declared)).status_code == 200
    media = (
        await expert.post(complete_url(garment), json={"media_id": ticket["media"]["id"]})
    ).json()
    assert media["status"] == "rejected"
    assert media["error_code"] == reason
    assert media["thumbnail_url"] is None
    assert await keys(app) == set()  # rejected bytes are not kept
    assert (await expert.get(f"/api/v1/media/{media['id']}/original")).status_code == 404


async def test_declared_type_and_size_are_checked_before_issuing_a_url(
    expert: httpx.AsyncClient, garment: dict[str, Any], settings: Settings
) -> None:
    gif = upload_body(b"GIF89a", content_type="image/gif")
    response = await expert.post(uploads_url(garment), json=gif)
    assert response.status_code == 415
    assert response.json()["error"]["code"] == "unsupported_media_type"

    big = {**upload_body(b"x"), "size_bytes": settings.upload_max_bytes + 1}
    response = await expert.post(uploads_url(garment), json=big)
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "upload_too_large"

    jpg_alias = await expert.post(
        uploads_url(garment), json=upload_body(b"x", content_type="image/JPG")
    )
    assert jpg_alias.status_code == 200


async def test_pixel_limit(
    make_settings: Callable[..., Settings],
    email_sender: RecordingEmailSender,
    clock: FakeClock,
    user: User,
) -> None:
    application = create_app(
        make_settings(image_max_pixels=1000), email_sender=email_sender, clock=clock
    )
    try:
        async with make_client(application) as http:
            await login(http, email_sender)
            garment = await create_garment(http)
            media = await upload_photo(http, garment["id"], make_jpeg((64, 48)))
            assert media["status"] == "rejected"
            assert media["error_code"] == "image_too_large"
    finally:
        await application.state.engine.dispose()


async def test_server_rejects_bytes_that_bypass_the_presigned_constraints(
    app: FastAPI, expert: httpx.AsyncClient, garment: dict[str, Any]
) -> None:
    """Defence in depth for providers that do not enforce the signed checksum."""
    data = make_jpeg()
    ticket = (await expert.post(uploads_url(garment), json=upload_body(data))).json()
    media_id = ticket["media"]["id"]
    await storage_of(app).put_bytes(
        staging_key(uuid.UUID(media_id)), make_jpeg((20, 20)), content_type="image/jpeg"
    )
    media = (await expert.post(complete_url(garment), json={"media_id": media_id})).json()
    assert media["status"] == "rejected"
    assert media["error_code"] == "checksum_mismatch"


async def test_object_larger_than_limit_is_rejected_without_reading_it_all(
    app: FastAPI, expert: httpx.AsyncClient, garment: dict[str, Any]
) -> None:
    data = make_jpeg()
    ticket = (await expert.post(uploads_url(garment), json=upload_body(data))).json()
    app.state.settings.upload_max_bytes = 100
    await storage_of(app).put_bytes(
        staging_key(uuid.UUID(ticket["media"]["id"])), data, content_type="image/jpeg"
    )
    media = (
        await expert.post(complete_url(garment), json={"media_id": ticket["media"]["id"]})
    ).json()
    assert media["error_code"] == "upload_too_large"


# --- Immutability ------------------------------------------------------------------------------


async def test_ready_original_cannot_be_replaced_through_an_old_upload_url(
    app: FastAPI, expert: httpx.AsyncClient, garment: dict[str, Any]
) -> None:
    data = make_jpeg()
    ticket = (await expert.post(uploads_url(garment), json=upload_body(data))).json()
    await put_to_storage(ticket["upload"], data)
    media = (
        await expert.post(complete_url(garment), json={"media_id": ticket["media"]["id"]})
    ).json()

    # The ticket only ever addressed the staging key; re-using it cannot touch the original.
    await put_to_storage(ticket["upload"], data)
    patched = await expert.patch(f"/api/v1/media/{media['id']}", json={"category": "defect"})
    assert patched.json()["category"] == "defect"
    for field in ("sha256", "size_bytes", "content_type", "width", "height", "completed_at"):
        assert patched.json()[field] == media[field]
    assert (await expert.get(media["original_url"])).content == data
    replay = await expert.post(complete_url(garment), json={"media_id": media["id"]})
    assert replay.json() == patched.json()


# --- Limits ------------------------------------------------------------------------------------


async def test_photo_limit_per_garment(
    app: FastAPI, expert: httpx.AsyncClient, garment: dict[str, Any]
) -> None:
    app.state.settings.garment_max_photos = 2
    for size in (10, 11):
        assert (
            await expert.post(uploads_url(garment), json=upload_body(make_jpeg((size, size))))
        ).status_code == 200
    response = await expert.post(uploads_url(garment), json=upload_body(make_jpeg((12, 12))))
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "media_limit_reached"


async def test_pending_upload_limit_per_user(
    app: FastAPI, expert: httpx.AsyncClient, garment: dict[str, Any]
) -> None:
    app.state.settings.pending_uploads_per_user = 1
    assert (
        await expert.post(uploads_url(garment), json=upload_body(make_jpeg()))
    ).status_code == 200
    response = await expert.post(uploads_url(garment), json=upload_body(make_jpeg((9, 9))))
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "too_many_pending_uploads"


# --- Deletion and cleanup ----------------------------------------------------------------------


async def test_deleting_a_photo_removes_its_objects(
    app: FastAPI, expert: httpx.AsyncClient, garment: dict[str, Any]
) -> None:
    keep = await upload_photo(expert, garment["id"], make_jpeg())
    drop = await upload_photo(expert, garment["id"], make_jpeg((30, 30)))
    assert (await expert.delete(f"/api/v1/media/{drop['id']}")).status_code == 204
    assert (await expert.get(drop["thumbnail_url"])).status_code == 404
    assert all(drop["id"] not in key for key in await keys(app))
    assert any(keep["id"] in key for key in await keys(app))
    detail = (await expert.get(f"/api/v1/garments/{garment['id']}")).json()
    assert [m["id"] for m in detail["media"]] == [keep["id"]]


async def test_deleting_a_garment_removes_all_objects(
    app: FastAPI, expert: httpx.AsyncClient, garment: dict[str, Any]
) -> None:
    media = await upload_photo(expert, garment["id"], make_jpeg())
    await expert.post(uploads_url(garment), json=upload_body(make_jpeg((5, 5))))  # pending
    assert await keys(app)
    assert (await expert.delete(f"/api/v1/garments/{garment['id']}")).status_code == 204
    assert await keys(app) == set()
    assert (await expert.get(media["thumbnail_url"])).status_code == 404


async def test_delete_survives_storage_outage_and_sweep_finishes_it(
    app: FastAPI,
    expert: httpx.AsyncClient,
    garment: dict[str, Any],
    make_settings: Callable[..., Settings],
    clock: FakeClock,
) -> None:
    await upload_photo(expert, garment["id"], make_jpeg())
    real_storage = app.state.storage
    app.state.storage = S3ObjectStorage(make_settings(storage_endpoint_url="http://127.0.0.1:9"))
    response = await expert.delete(f"/api/v1/garments/{garment['id']}")
    assert response.status_code == 204  # hidden immediately
    assert (await expert.get(f"/api/v1/garments/{garment['id']}")).status_code == 404
    app.state.storage = real_storage
    assert await keys(app) != set()  # objects still there (rows marked deleted)

    async with app.state.session_factory() as db:
        report = await StorageSweeper(db, app.state.settings, clock, real_storage).run()
    assert report.purged_media == 1
    assert report.purged_garments == 1
    assert await keys(app) == set()


async def test_storage_outage_is_reported_as_retryable(
    app: FastAPI,
    expert: httpx.AsyncClient,
    garment: dict[str, Any],
    make_settings: Callable[..., Settings],
) -> None:
    ticket = (await expert.post(uploads_url(garment), json=upload_body(make_jpeg()))).json()
    app.state.storage = S3ObjectStorage(make_settings(storage_endpoint_url="http://127.0.0.1:9"))
    response = await expert.post(complete_url(garment), json={"media_id": ticket["media"]["id"]})
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "storage_unavailable"
    assert response.headers["retry-after"]


async def test_sweep_removes_stale_uploads_rejections_and_orphans(
    app: FastAPI, expert: httpx.AsyncClient, garment: dict[str, Any], clock: FakeClock
) -> None:
    clock.now = datetime.now(UTC)
    ready = await upload_photo(expert, garment["id"], make_jpeg())
    stale = (await expert.post(uploads_url(garment), json=upload_body(make_jpeg((7, 7))))).json()
    await put_to_storage(stale["upload"], make_jpeg((7, 7)))  # uploaded, never completed
    storage = storage_of(app)
    orphan = f"originals/{garment['id']}/{uuid.uuid4()}"
    await storage.put_bytes(orphan, b"left over by a crash", content_type="image/jpeg")
    stray = f"uploads/{uuid.uuid4()}"  # late re-PUT after completion
    await storage.put_bytes(stray, b"stray", content_type="image/jpeg")

    clock.advance(hours=25)
    async with app.state.session_factory() as db:
        report = await StorageSweeper(db, app.state.settings, clock, storage).run()
    assert report.purged_media == 1  # the stale pending photo
    assert report.removed_orphan_objects == 1
    assert report.removed_staging_objects == 1  # stray (stale photo's object went with it)

    remaining = await keys(app)
    assert orphan not in remaining
    assert stray not in remaining
    assert all(stale["media"]["id"] not in key for key in remaining)
    assert any(ready["id"] in key for key in remaining)
    detail = (await expert.get(f"/api/v1/garments/{garment['id']}")).json()
    assert [m["id"] for m in detail["media"]] == [ready["id"]]


async def test_upload_flow_does_not_log_filenames_or_urls(
    expert: httpx.AsyncClient, garment: dict[str, Any], caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.DEBUG):
        ticket = (
            await expert.post(
                uploads_url(garment), json=upload_body(b"<html>", filename="secret-name.jpg")
            )
        ).json()
        await put_to_storage(ticket["upload"], b"<html>")
        await expert.post(complete_url(garment), json={"media_id": ticket["media"]["id"]})
    # `httpx` records come from the test's own client, which plays the browser.
    server_records = [r for r in caplog.records if not r.name.startswith("httpx")]
    text = "\n".join(r.getMessage() + str(getattr(r, "fields", "")) for r in server_records)
    assert "secret-name" not in text
    assert "X-Amz-Signature" not in text
    assert "media_rejected" in text
