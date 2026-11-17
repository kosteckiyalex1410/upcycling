"""Voice notes against real PostgreSQL and S3-compatible storage (ADR-0007)."""

import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi import FastAPI

from app.application.garments import StorageSweeper
from app.domain.users import User
from app.domain.voice_notes import voice_note_audio_key, voice_note_staging_key
from app.infrastructure.storage import S3ObjectStorage
from tests.conftest import FakeClock, RecordingEmailSender, create_user, login, make_client
from tests.media_helpers import (
    AUDIO,
    CHROMIUM_RECORDING,
    WEBKIT_RECORDING,
    create_garment,
    put_to_storage,
    upload_voice_note,
    voice_body,
)


@pytest.fixture
async def expert(
    client: httpx.AsyncClient, email_sender: RecordingEmailSender, user: User
) -> httpx.AsyncClient:
    await login(client, email_sender)
    return client


@pytest.fixture
async def garment(expert: httpx.AsyncClient) -> dict[str, Any]:
    return await create_garment(expert, "Blazer")


def uploads_url(garment: dict[str, Any]) -> str:
    return f"/api/v1/garments/{garment['id']}/voice-notes/uploads"


def complete_url(garment: dict[str, Any]) -> str:
    return f"/api/v1/garments/{garment['id']}/voice-notes/complete"


async def keys(app: FastAPI) -> set[str]:
    storage: S3ObjectStorage = app.state.storage
    return {obj.key for obj in await storage.list_objects("")}


async def test_safari_and_chrome_recordings_are_stored_byte_for_byte(
    app: FastAPI, expert: httpx.AsyncClient, garment: dict[str, Any]
) -> None:
    mp4 = await upload_voice_note(expert, garment["id"], WEBKIT_RECORDING)
    webm = await upload_voice_note(
        expert, garment["id"], CHROMIUM_RECORDING, content_type="audio/webm;codecs=opus"
    )
    assert (mp4["status"], mp4["content_type"], mp4["codec"]) == ("ready", "audio/mp4", "aac")
    assert (webm["content_type"], webm["codec"]) == ("audio/webm", "opus")
    assert 2300 < mp4["duration_ms"] < 2500
    assert mp4["recorded_at"] == "2026-11-17T10:00:00Z"

    played = await expert.get(mp4["audio_url"])
    assert played.status_code == 200
    assert played.content == WEBKIT_RECORDING
    assert played.headers["content-type"] == "audio/mp4"
    assert played.headers["accept-ranges"] == "bytes"
    assert played.headers["cache-control"] == "private, no-cache"

    garment_id, note_id = uuid.UUID(garment["id"]), uuid.UUID(mp4["id"])
    stored = await keys(app)
    assert voice_note_audio_key(garment_id, note_id) in stored
    assert voice_note_staging_key(note_id) not in stored

    detail = (await expert.get(f"/api/v1/garments/{garment['id']}")).json()
    assert [n["id"] for n in detail["voice_notes"]] == [mp4["id"], webm["id"]]
    assert detail["media"] == []


async def test_playback_supports_byte_ranges_for_safari(
    expert: httpx.AsyncClient, garment: dict[str, Any]
) -> None:
    note = await upload_voice_note(expert, garment["id"])
    size = len(WEBKIT_RECORDING)

    probe = await expert.get(note["audio_url"], headers={"Range": "bytes=0-1"})
    assert probe.status_code == 206
    assert probe.content == WEBKIT_RECORDING[:2]
    assert probe.headers["content-range"] == f"bytes 0-1/{size}"
    assert probe.headers["content-length"] == "2"

    tail = await expert.get(note["audio_url"], headers={"Range": "bytes=-100"})
    assert tail.content == WEBKIT_RECORDING[-100:]

    bad = await expert.get(note["audio_url"], headers={"Range": f"bytes={size}-"})
    assert bad.status_code == 416
    assert bad.headers["content-range"] == f"bytes */{size}"

    etag = probe.headers["etag"]
    assert (await expert.get(note["audio_url"], headers={"If-None-Match": etag})).status_code == 304


async def test_every_step_can_be_retried(
    expert: httpx.AsyncClient, garment: dict[str, Any]
) -> None:
    body = voice_body(WEBKIT_RECORDING)
    first = (await expert.post(uploads_url(garment), json=body)).json()
    note_id = first["voice_note"]["id"]

    # Completing before the bytes arrived (e.g. the PUT was interrupted): retryable.
    early = await expert.post(complete_url(garment), json={"voice_note_id": note_id})
    assert early.status_code == 409
    assert early.json()["error"]["code"] == "upload_incomplete"

    again = (await expert.post(uploads_url(garment), json=body)).json()
    assert again["voice_note"]["id"] == note_id
    assert again["upload"]["url"]  # fresh URL for the same note
    assert (await put_to_storage(again["upload"], WEBKIT_RECORDING)).status_code == 200
    done = await expert.post(complete_url(garment), json={"voice_note_id": note_id})
    replay = await expert.post(complete_url(garment), json={"voice_note_id": note_id})
    assert done.json()["status"] == replay.json()["status"] == "ready"

    finished = (await expert.post(uploads_url(garment), json=body)).json()
    assert finished["upload"] is None
    assert finished["voice_note"]["status"] == "ready"

    other = {**body, "sha256": "0" * 64}
    conflict = await expert.post(uploads_url(garment), json=other)
    assert conflict.json()["error"]["code"] == "idempotency_conflict"


@pytest.mark.parametrize(
    ("fixture", "declared", "code"),
    [
        ("video.mp4", "audio/mp4", "unsupported_media_type"),
        ("truncated.mp4", "audio/mp4", "invalid_audio"),
        ("too-long.webm", "audio/webm", "audio_too_long"),
        # Bytes are WebM but the client declared MP4.
        ("chromium-recording.webm", "audio/mp4", "unsupported_media_type"),
    ],
)
async def test_bad_recordings_are_rejected_after_upload_and_not_kept(
    app: FastAPI,
    expert: httpx.AsyncClient,
    garment: dict[str, Any],
    fixture: str,
    declared: str,
    code: str,
) -> None:
    data = (Path(AUDIO) / fixture).read_bytes()
    ticket = (
        await expert.post(
            uploads_url(garment), json=voice_body(data, content_type=declared, duration_ms=None)
        )
    ).json()
    await put_to_storage(ticket["upload"], data)
    note = (
        await expert.post(complete_url(garment), json={"voice_note_id": ticket["voice_note"]["id"]})
    ).json()
    assert (note["status"], note["error_code"], note["audio_url"]) == ("rejected", code, None)
    assert await keys(app) == set()


@pytest.mark.parametrize(
    ("changes", "status", "code"),
    [
        ({"content_type": "audio/wav"}, 415, "unsupported_media_type"),
        ({"content_type": "video/mp4"}, 415, "unsupported_media_type"),
        ({"size_bytes": 21 * 1024 * 1024}, 413, "upload_too_large"),
        ({"duration_ms": 6 * 60 * 1000}, 413, "audio_too_long"),
        ({"duration_ms": -1}, 422, "validation_failed"),
    ],
)
async def test_declared_values_are_checked_before_issuing_a_url(
    expert: httpx.AsyncClient,
    garment: dict[str, Any],
    changes: dict[str, Any],
    status: int,
    code: str,
) -> None:
    response = await expert.post(uploads_url(garment), json=voice_body(b"x") | changes)
    assert response.status_code == status
    assert response.json()["error"]["code"] == code


async def test_voice_note_limit_per_garment(
    app: FastAPI, expert: httpx.AsyncClient, garment: dict[str, Any]
) -> None:
    app.state.settings.garment_max_voice_notes = 1
    await upload_voice_note(expert, garment["id"])
    response = await expert.post(uploads_url(garment), json=voice_body(b"second"))
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "voice_note_limit_reached"


async def test_deleting_a_voice_note_removes_audio_and_metadata(
    app: FastAPI, expert: httpx.AsyncClient, garment: dict[str, Any]
) -> None:
    drop = await upload_voice_note(expert, garment["id"])
    keep = await upload_voice_note(expert, garment["id"])
    assert (await expert.delete(f"/api/v1/voice-notes/{drop['id']}")).status_code == 204
    assert (await expert.get(drop["audio_url"])).status_code == 404
    assert (await expert.delete(f"/api/v1/voice-notes/{drop['id']}")).status_code == 404
    stored = await keys(app)
    assert all(drop["id"] not in key for key in stored)
    assert any(keep["id"] in key for key in stored)
    detail = (await expert.get(f"/api/v1/garments/{garment['id']}")).json()
    assert [n["id"] for n in detail["voice_notes"]] == [keep["id"]]


async def test_deleting_a_garment_removes_its_voice_notes(
    app: FastAPI, expert: httpx.AsyncClient, garment: dict[str, Any]
) -> None:
    note = await upload_voice_note(expert, garment["id"])
    assert (await expert.delete(f"/api/v1/garments/{garment['id']}")).status_code == 204
    assert (await expert.get(note["audio_url"])).status_code == 404
    assert await keys(app) == set()


async def test_other_users_and_signed_out_requests_cannot_reach_voice_notes(
    app: FastAPI,
    expert: httpx.AsyncClient,
    garment: dict[str, Any],
    email_sender: RecordingEmailSender,
) -> None:
    note = await upload_voice_note(expert, garment["id"])
    attempts: list[tuple[str, str, dict[str, Any] | None]] = [
        ("POST", uploads_url(garment), voice_body(b"x")),
        ("POST", complete_url(garment), {"voice_note_id": note["id"]}),
        ("GET", note["audio_url"], None),
        ("DELETE", f"/api/v1/voice-notes/{note['id']}", None),
    ]
    async with make_client(app, ip="198.51.100.9") as anonymous:
        for method, path, body in attempts:
            response = await anonymous.request(method, path, json=body)
            assert response.status_code == 401, (method, path)

    await create_user(app, "intruder@example.com")
    async with make_client(app, ip="198.51.100.7") as intruder:
        await login(intruder, email_sender, "intruder@example.com")
        for method, path, body in attempts:
            response = await intruder.request(method, path, json=body)
            assert response.status_code == 404, (method, path, response.text)
            assert response.json()["error"]["code"] == "not_found"

    assert (await expert.get(note["audio_url"])).status_code == 200


async def test_sweep_removes_abandoned_recordings_and_orphan_audio(
    app: FastAPI, expert: httpx.AsyncClient, garment: dict[str, Any], clock: FakeClock
) -> None:
    clock.now = datetime.now(UTC)
    ready = await upload_voice_note(expert, garment["id"])
    abandoned = (await expert.post(uploads_url(garment), json=voice_body(WEBKIT_RECORDING))).json()
    await put_to_storage(abandoned["upload"], WEBKIT_RECORDING)  # never completed
    storage: S3ObjectStorage = app.state.storage
    orphan = voice_note_audio_key(uuid.UUID(garment["id"]), uuid.uuid4())
    await storage.put_bytes(orphan, b"left over by a crash", content_type="audio/mp4")

    clock.advance(hours=25)
    async with app.state.session_factory() as db:
        report = await StorageSweeper(db, app.state.settings, clock, storage).run()
    assert report.purged_voice_notes == 1
    assert report.removed_orphan_objects == 1

    remaining = await keys(app)
    assert remaining == {voice_note_audio_key(uuid.UUID(garment["id"]), uuid.UUID(ready["id"]))}
    detail = (await expert.get(f"/api/v1/garments/{garment['id']}")).json()
    assert [n["id"] for n in detail["voice_notes"]] == [ready["id"]]
