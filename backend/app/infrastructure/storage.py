"""S3-compatible implementation of `ObjectStorage` (ADR-0006), using boto3 in worker threads.

Works with any S3-compatible provider (AWS S3, Cloudflare R2, SeaweedFS, ...). Credentials
stay server-side; browsers only receive short-lived presigned URLs.
"""

import asyncio
import base64
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING, BinaryIO

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

from app.application.ports import (
    ObjectMissingError,
    ObjectTooLargeError,
    StorageUnavailableError,
    StoredObject,
)
from app.config import Settings

if TYPE_CHECKING:
    from botocore.response import StreamingBody
    from types_boto3_s3.client import S3Client

_CHUNK = 1024 * 1024
_NOT_FOUND = {"404", "NoSuchKey", "NotFound"}
# Headers the browser must send with a presigned upload; also the bucket CORS allow-list.
UPLOAD_HEADERS = ("content-type", "x-amz-checksum-sha256")


def _client(settings: Settings, endpoint_url: str) -> "S3Client":
    return boto3.client(
        "s3",
        endpoint_url=endpoint_url,
        region_name=settings.storage_region,
        aws_access_key_id=settings.storage_access_key_id,
        aws_secret_access_key=settings.storage_secret_access_key.get_secret_value(),
        config=Config(
            signature_version="s3v4",
            s3={"addressing_style": settings.storage_addressing_style},
            connect_timeout=5,
            read_timeout=30,
            retries={"max_attempts": 3, "mode": "standard"},
            # Only send/verify checksums when an operation requires them; presigned uploads
            # carry an explicit SHA-256 instead.
            request_checksum_calculation="when_required",
            response_checksum_validation="when_required",
        ),
    )


def _is_not_found(exc: ClientError) -> bool:
    return str(exc.response.get("Error", {}).get("Code")) in _NOT_FOUND


def hex_to_b64(sha256_hex: str) -> str:
    return base64.b64encode(bytes.fromhex(sha256_hex)).decode("ascii")


class S3ObjectStorage:
    def __init__(self, settings: Settings) -> None:
        self._bucket = settings.storage_bucket
        self._client = _client(settings, settings.storage_endpoint_url)
        # Presigning is local computation; the host in the signature must be the one the
        # browser connects to.
        self._presign_client = _client(settings, settings.storage_presign_endpoint_url)

    @property
    def client(self) -> "S3Client":
        return self._client

    @property
    def bucket(self) -> str:
        return self._bucket

    def presign_put(
        self, key: str, *, content_type: str, size_bytes: int, sha256_b64: str, expires_in: int
    ) -> tuple[str, dict[str, str]]:
        url = self._presign_client.generate_presigned_url(
            "put_object",
            Params={
                "Bucket": self._bucket,
                "Key": key,
                "ContentType": content_type,
                "ContentLength": size_bytes,
                "ChecksumSHA256": sha256_b64,
            },
            ExpiresIn=expires_in,
        )
        # Content-Length is set by the browser from the body and is part of the signature.
        return url, {"Content-Type": content_type, "x-amz-checksum-sha256": sha256_b64}

    async def head(self, key: str) -> StoredObject | None:
        try:
            response = await asyncio.to_thread(
                self._client.head_object, Bucket=self._bucket, Key=key
            )
        except ClientError as exc:
            if _is_not_found(exc):
                return None
            raise StorageUnavailableError from exc
        except BotoCoreError as exc:
            raise StorageUnavailableError from exc
        return StoredObject(
            key=key, size_bytes=response["ContentLength"], last_modified=response["LastModified"]
        )

    async def _get_body(self, key: str) -> "StreamingBody":
        try:
            response = await asyncio.to_thread(
                self._client.get_object, Bucket=self._bucket, Key=key
            )
        except ClientError as exc:
            if _is_not_found(exc):
                raise ObjectMissingError(key) from exc
            raise StorageUnavailableError from exc
        except BotoCoreError as exc:
            raise StorageUnavailableError from exc
        body: StreamingBody = response["Body"]
        return body

    async def download(self, key: str, destination: BinaryIO, *, max_bytes: int) -> int:
        body = await self._get_body(key)
        written = 0
        try:
            while chunk := await asyncio.to_thread(body.read, _CHUNK):
                written += len(chunk)
                if written > max_bytes:
                    raise ObjectTooLargeError(key)
                destination.write(chunk)
        except BotoCoreError as exc:
            raise StorageUnavailableError from exc
        finally:
            body.close()
        return written

    async def open_stream(self, key: str) -> AsyncIterator[bytes]:
        body = await self._get_body(key)

        async def chunks() -> AsyncIterator[bytes]:
            try:
                while chunk := await asyncio.to_thread(body.read, _CHUNK):
                    yield chunk
            finally:
                body.close()

        return chunks()

    async def read_bytes(self, key: str) -> bytes:
        body = await self._get_body(key)
        try:
            data: bytes = await asyncio.to_thread(body.read)
        except BotoCoreError as exc:
            raise StorageUnavailableError from exc
        finally:
            body.close()
        return data

    async def upload(self, key: str, source: BinaryIO, *, content_type: str) -> None:
        source.seek(0)
        try:
            await asyncio.to_thread(
                self._client.upload_fileobj,
                source,
                self._bucket,
                key,
                ExtraArgs={"ContentType": content_type},
            )
        except (ClientError, BotoCoreError) as exc:
            raise StorageUnavailableError from exc

    async def put_bytes(self, key: str, data: bytes, *, content_type: str) -> None:
        try:
            await asyncio.to_thread(
                self._client.put_object,
                Bucket=self._bucket,
                Key=key,
                Body=data,
                ContentType=content_type,
            )
        except (ClientError, BotoCoreError) as exc:
            raise StorageUnavailableError from exc

    async def delete_many(self, keys: list[str]) -> None:
        # One request per key: DeleteObjects needs Content-MD5/checksums that some
        # S3-compatible stores handle inconsistently, and photos own at most four keys.
        for key in keys:
            try:
                await asyncio.to_thread(self._client.delete_object, Bucket=self._bucket, Key=key)
            except ClientError as exc:
                if not _is_not_found(exc):
                    raise StorageUnavailableError from exc
            except BotoCoreError as exc:
                raise StorageUnavailableError from exc

    async def list_objects(self, prefix: str) -> list[StoredObject]:
        def collect() -> list[StoredObject]:
            paginator = self._client.get_paginator("list_objects_v2")
            return [
                StoredObject(
                    key=item["Key"], size_bytes=item["Size"], last_modified=item["LastModified"]
                )
                for page in paginator.paginate(Bucket=self._bucket, Prefix=prefix)
                for item in page.get("Contents", [])
            ]

        try:
            return await asyncio.to_thread(collect)
        except (ClientError, BotoCoreError) as exc:
            raise StorageUnavailableError from exc

    async def ensure_bucket(self, *, cors_origins: list[str]) -> None:
        """Create the bucket if missing and allow presigned PUTs from the PWA origins only.
        Development/CI convenience; production buckets are provisioned by the operator,
        but the same CORS rule applies (docs/development.md)."""

        def run() -> None:
            try:
                self._client.head_bucket(Bucket=self._bucket)
            except ClientError as exc:
                if not _is_not_found(exc):
                    raise
                self._client.create_bucket(Bucket=self._bucket)
            self._client.put_bucket_cors(
                Bucket=self._bucket,
                CORSConfiguration={
                    "CORSRules": [
                        {
                            "AllowedOrigins": sorted(cors_origins),
                            "AllowedMethods": ["PUT"],
                            "AllowedHeaders": list(UPLOAD_HEADERS),
                            "ExposeHeaders": ["ETag"],
                            "MaxAgeSeconds": 600,
                        }
                    ]
                },
            )

        await asyncio.to_thread(run)
