"""Garment projects: CRUD, idempotent create, pagination, authentication and ownership."""

import re
import uuid

import httpx
import pytest
from fastapi import FastAPI

from app.domain.users import User
from tests.conftest import RecordingEmailSender, create_user, login, make_client
from tests.media_helpers import create_garment, make_jpeg, upload_photo

GARMENTS = "/api/v1/garments"


@pytest.fixture
async def expert(
    client: httpx.AsyncClient, email_sender: RecordingEmailSender, user: User
) -> httpx.AsyncClient:
    await login(client, email_sender)
    return client


async def test_create_is_idempotent_and_trims_text(expert: httpx.AsyncClient) -> None:
    key = str(uuid.uuid4())
    body = {"client_request_id": key, "title": "  Denim jacket  ", "notes": "   "}
    first = await expert.post(GARMENTS, json=body)
    assert first.status_code == 201
    created = first.json()
    assert created["title"] == "Denim jacket"
    assert created["notes"] is None
    assert created["media"] == []

    replay = await expert.post(GARMENTS, json=body)
    assert replay.status_code == 200
    assert replay.json()["id"] == created["id"]
    assert len((await expert.get(GARMENTS)).json()["items"]) == 1


async def test_get_update_and_delete(expert: httpx.AsyncClient) -> None:
    garment = await create_garment(expert, "Coat")
    url = f"{GARMENTS}/{garment['id']}"

    updated = await expert.patch(url, json={"notes": "Wool, moth hole on sleeve"})
    assert updated.status_code == 200
    assert updated.json()["title"] == "Coat"  # absent field unchanged
    assert updated.json()["notes"] == "Wool, moth hole on sleeve"

    cleared = await expert.patch(url, json={"title": None})
    assert cleared.json()["title"] is None
    assert cleared.json()["notes"] == "Wool, moth hole on sleeve"

    assert (await expert.get(url)).json()["id"] == garment["id"]
    assert (await expert.delete(url)).status_code == 204
    assert (await expert.get(url)).status_code == 404
    assert (await expert.delete(url)).status_code == 404
    assert (await expert.get(GARMENTS)).json()["items"] == []


async def test_update_rejects_unknown_fields_and_long_title(expert: httpx.AsyncClient) -> None:
    garment = await create_garment(expert)
    url = f"{GARMENTS}/{garment['id']}"
    assert (await expert.patch(url, json={"owner_id": str(uuid.uuid4())})).status_code == 422
    response = await expert.patch(url, json={"title": "x" * 121})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_failed"


async def test_list_is_newest_first_with_cursor_pagination(expert: httpx.AsyncClient) -> None:
    ids = [(await create_garment(expert, f"G{i}"))["id"] for i in range(5)]
    first = (await expert.get(GARMENTS, params={"limit": 2})).json()
    assert [item["id"] for item in first["items"]] == ids[::-1][:2]
    second = (
        await expert.get(GARMENTS, params={"limit": 2, "cursor": first["next_cursor"]})
    ).json()
    third = (
        await expert.get(GARMENTS, params={"limit": 2, "cursor": second["next_cursor"]})
    ).json()
    assert [i["id"] for i in second["items"] + third["items"]] == ids[::-1][2:]
    assert third["next_cursor"] is None


async def test_cover_falls_back_to_an_uncategorized_photo(expert: httpx.AsyncClient) -> None:
    garment = await create_garment(expert)
    photo = await upload_photo(expert, garment["id"], make_jpeg(), category=None)
    item = (await expert.get(GARMENTS)).json()["items"][0]
    assert item["cover_thumbnail_url"] == photo["thumbnail_url"]


async def test_list_shows_photo_count_and_front_cover(expert: httpx.AsyncClient) -> None:
    garment = await create_garment(expert)
    await upload_photo(expert, garment["id"], make_jpeg(), category="detail")
    front = await upload_photo(expert, garment["id"], make_jpeg((50, 50)), category="front")
    item = (await expert.get(GARMENTS)).json()["items"][0]
    assert item["photo_count"] == 2
    assert item["cover_thumbnail_url"] == front["thumbnail_url"]


def _all_routes(app: FastAPI) -> list[tuple[str, str]]:
    return [
        (method.upper(), re.sub(r"\{[^}]+\}", str(uuid.uuid4()), path))
        for path, operations in app.openapi()["paths"].items()
        for method in operations
        if path.startswith(("/api/v1/garments", "/api/v1/media", "/api/v1/voice-notes"))
    ]


async def test_every_garment_and_media_endpoint_requires_authentication(
    app: FastAPI, client: httpx.AsyncClient
) -> None:
    routes = _all_routes(app)
    assert len(routes) >= 15
    for method, path in routes:
        response = await client.request(method, path, json={})
        assert response.status_code == 401, (method, path)
        assert response.json()["error"]["code"] == "unauthenticated"


async def test_other_users_cannot_see_or_touch_garments_or_photos(
    app: FastAPI, expert: httpx.AsyncClient, email_sender: RecordingEmailSender
) -> None:
    garment = await create_garment(expert, "Private")
    photo = await upload_photo(expert, garment["id"], make_jpeg())
    g, m = garment["id"], photo["id"]

    await create_user(app, "intruder@example.com")
    async with make_client(app, ip="198.51.100.7") as intruder:
        await login(intruder, email_sender, "intruder@example.com")
        assert (await intruder.get(GARMENTS)).json()["items"] == []
        attempts = [
            ("GET", f"{GARMENTS}/{g}", None),
            ("PATCH", f"{GARMENTS}/{g}", {"title": "mine"}),
            ("DELETE", f"{GARMENTS}/{g}", None),
            (
                "POST",
                f"{GARMENTS}/{g}/media/uploads",
                {
                    "client_upload_id": str(uuid.uuid4()),
                    "category": "front",
                    "content_type": "image/jpeg",
                    "size_bytes": 10,
                    "sha256": "0" * 64,
                },
            ),
            ("POST", f"{GARMENTS}/{g}/media/complete", {"media_id": m}),
            ("PATCH", f"/api/v1/media/{m}", {"category": "back"}),
            ("DELETE", f"/api/v1/media/{m}", None),
            ("GET", f"/api/v1/media/{m}/thumbnail", None),
            ("GET", f"/api/v1/media/{m}/preview", None),
            ("GET", f"/api/v1/media/{m}/original", None),
        ]
        for method, path, body in attempts:
            response = await intruder.request(method, path, json=body)
            assert response.status_code == 404, (method, path, response.text)
            assert response.json()["error"]["code"] == "not_found"

    # Nothing changed for the owner.
    detail = (await expert.get(f"{GARMENTS}/{g}")).json()
    assert detail["title"] == "Private"
    assert [item["category"] for item in detail["media"]] == ["front"]
    assert (await expert.get(f"/api/v1/media/{m}/original")).status_code == 200
